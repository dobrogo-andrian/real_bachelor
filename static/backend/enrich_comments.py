import argparse
import logging
import os
import re
import unicodedata
import warnings
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import pyodbc
from lingua.lingua import Language, LanguageDetectorBuilder
from peft import PeftModel
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

from static.backend import db_connection

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("filelock").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

SUPPORTED_LANGUAGES = {"uk", "ru", "en", "other", "symbols_only"}
DEFAULT_SENTIMENT = "neutral"
BASE_MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
BASE_MODEL_REVISION = "refs/pr/15"
ADAPTER_DIR = Path(__file__).resolve().parents[2] / "model_fine_tuning" / "sentiment_lora_adapters"
INFERENCE_BATCH_SIZE = int(os.getenv("INFERENCE_BATCH_SIZE", "32"))
DB_FETCH_BATCH_SIZE = int(os.getenv("ENRICH_DB_FETCH_BATCH_SIZE", "512"))
LINGUA_LANGUAGE_MAP = {
    Language.UKRAINIAN: "uk",
    Language.RUSSIAN: "ru",
    Language.ENGLISH: "en",
}
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\w+")

os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")

warnings.filterwarnings(
    "ignore",
    message="`clean_up_tokenization_spaces` was not set.*",
    category=FutureWarning,
)

LABEL_MAP = {
    "label_0": "negative",
    "label_1": "neutral",
    "label_2": "positive",
    "negative": "negative",
    "neutral": "neutral",
    "positive": "positive",
}


def normalize_unicode(text):
    return unicodedata.normalize("NFC", text)


def normalize_comment_for_analysis(text):
    if not text:
        return ""

    text = normalize_unicode(text)
    text = URL_PATTERN.sub("http", text)
    text = MENTION_PATTERN.sub("@user", text)
    return " ".join(text.split())


def _contains_letters(text):
    return any(char.isalpha() for char in text)


@lru_cache(maxsize=1)
def get_language_detector():
    return LanguageDetectorBuilder.from_all_languages().build()


def _detect_with_lingua(text):
    try:
        detected_language = get_language_detector().detect_language_of(text)
    except Exception:
        return "other"

    return LINGUA_LANGUAGE_MAP.get(detected_language, "other")


def detect_main_language(comment):
    if not comment or not comment.strip():
        return "symbols_only"

    if not _contains_letters(comment):
        return "symbols_only"

    normalized_comment = normalize_unicode(comment)
    if not normalized_comment or not _contains_letters(normalized_comment):
        return "symbols_only"

    try:
        return _detect_with_lingua(normalized_comment)
    except Exception:
        return "other"


@lru_cache(maxsize=1)
def load_models():
    if not ADAPTER_DIR.exists():
        raise FileNotFoundError(f"Fine-tuned LoRA adapter directory not found: {ADAPTER_DIR}")

    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_NAME,
        revision=BASE_MODEL_REVISION,
        use_fast=True,
        clean_up_tokenization_spaces=False,
    )

    base_model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL_NAME,
        revision=BASE_MODEL_REVISION,
        use_safetensors=True,
    )

    peft_model = PeftModel.from_pretrained(base_model, str(ADAPTER_DIR))

    model = peft_model.merge_and_unload()
    model.eval()

    print(f"[sentiment] loaded base model: {BASE_MODEL_NAME} @ {BASE_MODEL_REVISION}")
    print(f"[sentiment] loaded and merged fine-tuned LoRA adapters: {ADAPTER_DIR}")

    return pipeline(
        "text-classification",
        model=model,
        tokenizer=tokenizer,
        framework="pt",
        truncation=True,
        max_length=128,
    )


def analyze_sentiment_batch(comments, classifier, batch_size=INFERENCE_BATCH_SIZE):
    if not comments:
        return []

    try:
        results = classifier(
            comments,
            batch_size=batch_size,
            truncation=True,
            max_length=128,
        )
    except Exception:
        return [DEFAULT_SENTIMENT] * len(comments)

    sentiments = []
    for result in results:
        label = str(result.get("label", "")).lower()
        sentiments.append(LABEL_MAP.get(label, DEFAULT_SENTIMENT))
    return sentiments


def build_comment_query(mode, page_name=None, page_id=None):
    base_query = """
                 SELECT c.[CommentHash],
                        c.[PageName],
                        c.[PageID],
                        c.[PostHref],
                        c.[PostTime],
                        c.[Comment],
                        c.[CommentTime],
                        c.[CommentLikes],
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                ISNULL(c.[PageID], N''),
                                ISNULL(c.[PostHref], N''),
                                c.[PostTime]
                            ORDER BY
                                CASE WHEN c.[CommentTime] IS NULL THEN 1 ELSE 0 END,
                                c.[CommentTime],
                                c.[CommentHash]
                        ) AS [CommentOrder]
                 FROM [dbo].[Comments] AS c \
                 """

    conditions = []
    params = []

    if mode == "delta":
        base_query += """
        LEFT JOIN [dbo].[EnrichedComments] AS ec
            ON ec.[CommentHash] = c.[CommentHash]
        """
        conditions.append("ec.[CommentHash] IS NULL")

    if mode == "page_name":
        if not page_name:
            raise ValueError("`page_name` is required for mode `page_name`.")
        conditions.append("c.[PageName] = ?")
        params.append(page_name)

    if mode == "page_id":
        if not page_id:
            raise ValueError("`page_id` is required for mode `page_id`.")
        conditions.append("c.[PageID] = ?")
        params.append(page_id)

    if conditions:
        base_query += "\nWHERE " + "\n  AND ".join(conditions)

    base_query += "\nORDER BY c.[PageID], c.[PostTime], c.[CommentTime], c.[CommentHash]"
    return base_query, params


def normalize_comment_payload(comment):
    if comment is None:
        return ""
    return normalize_unicode(str(comment))


def normalize_datetime_value(value):
    if value is None:
        return None
    return value.replace(microsecond=0)


def build_post_group_key(row):
    page_id = row.get("PageID")
    post_href = row.get("PostHref")
    post_time = normalize_datetime_value(row.get("PostTime"))
    return (
        str(page_id).strip() if page_id is not None else "",
        str(post_href).strip() if post_href is not None else "",
        post_time.isoformat(sep=" ") if post_time else "",
    )


def assign_comment_order(comment_rows):
    grouped_rows = {}
    for row in comment_rows:
        grouped_rows.setdefault(build_post_group_key(row), []).append(row)

    comment_order_by_hash = {}
    for rows in grouped_rows.values():
        ordered_rows = sorted(
            rows,
            key=lambda current_row: (
                current_row.get("CommentTime") is None,
                normalize_datetime_value(current_row.get("CommentTime")) or datetime.max,
                str(current_row.get("CommentHash") or ""),
            ),
        )
        for index, row in enumerate(ordered_rows, start=1):
            comment_order_by_hash[row["CommentHash"]] = index

    return comment_order_by_hash


def iter_comment_row_batches(conn, mode, page_name=None, page_id=None, fetch_size=DB_FETCH_BATCH_SIZE):
    query, params = build_comment_query(mode, page_name=page_name, page_id=page_id)
    cursor = conn.cursor()
    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]

    try:
        while True:
            raw_rows = cursor.fetchmany(fetch_size)
            if not raw_rows:
                break
            yield [dict(zip(columns, raw_row)) for raw_row in raw_rows]
    finally:
        cursor.close()


def clear_enriched_scope(conn, mode, page_name=None, page_id=None):
    cursor = conn.cursor()
    try:
        if mode == "whole_db":
            cursor.execute("TRUNCATE TABLE [dbo].[EnrichedComments]")
        elif mode == "page_name":
            cursor.execute(
                "DELETE FROM [dbo].[EnrichedComments] WHERE [PageName] = ?",
                page_name,
            )
        elif mode == "page_id":
            cursor.execute(
                "DELETE FROM [dbo].[EnrichedComments] WHERE [PageID] = ?",
                page_id,
            )
        else:
            return 0

        deleted_count = cursor.rowcount if cursor.rowcount != -1 else 0
        conn.commit()
        return deleted_count
    finally:
        cursor.close()


def prepare_enriched_rows(comment_rows, models, source):
    processed_time = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    enriched_rows = []
    comment_order_by_hash = None
    if any(row.get("CommentOrder") is None for row in comment_rows):
        comment_order_by_hash = assign_comment_order(comment_rows)
    normalized_comments = []

    for row in comment_rows:
        comment_order = row.get("CommentOrder")
        if comment_order is None and comment_order_by_hash is not None:
            comment_order = comment_order_by_hash.get(row["CommentHash"])
        normalized_comment = normalize_comment_payload(row["Comment"])
        normalized_analysis_comment = normalize_comment_for_analysis(normalized_comment)
        main_language = detect_main_language(normalized_comment)
        if main_language not in SUPPORTED_LANGUAGES:
            main_language = "other"
        normalized_comments.append(normalized_analysis_comment)
        enriched_rows.append({
            "CommentHash": row["CommentHash"],
            "PageName": row["PageName"],
            "PageID": row["PageID"],
            "PostHref": row.get("PostHref"),
            "PostTime": normalize_datetime_value(row["PostTime"]),
            "CommentTime": normalize_datetime_value(row["CommentTime"]),
            "CommentOrder": comment_order,
            "CommentLikes": 0 if comment_order == 1 else row["CommentLikes"],
            "MainLanguage": main_language,
            "NormalizedComment": normalized_analysis_comment,
            "Sentiment": DEFAULT_SENTIMENT,
            "ProcessedTime": processed_time,
            "Source": source,
        })

    non_empty_comments = [comment for comment in normalized_comments if comment]
    predicted_sentiments = iter(analyze_sentiment_batch(non_empty_comments, models))
    for row, normalized_comment in zip(enriched_rows, normalized_comments):
        if normalized_comment:
            sentiment = next(predicted_sentiments, DEFAULT_SENTIMENT)
            if sentiment in {"positive", "neutral", "negative"}:
                row["Sentiment"] = sentiment

    return enriched_rows


def upsert_enriched_rows(conn, rows, allow_updates=True):
    if not rows:
        return {"processed": 0, "added_count": 0, "updated_count": 0}

    cursor = conn.cursor()
    cursor.fast_executemany = True
    cursor.setinputsizes([
        (pyodbc.SQL_WVARCHAR, 64, 0),
        (pyodbc.SQL_WVARCHAR, 100, 0),
        (pyodbc.SQL_WVARCHAR, 100, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_INTEGER, 0, 0),
        (pyodbc.SQL_INTEGER, 0, 0),
        (pyodbc.SQL_WVARCHAR, 20, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_WVARCHAR, 20, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_WVARCHAR, 50, 0),
    ])
    deduplicated_rows = list(_deduplicate_rows_by_hash(rows))
    params = [
        (
            row["CommentHash"],
            row["PageName"],
            row["PageID"],
            row["PostHref"],
            row["PostTime"],
            row["CommentTime"],
            row["CommentOrder"],
            row["CommentLikes"],
            row["MainLanguage"],
            row["NormalizedComment"],
            row["Sentiment"],
            row["ProcessedTime"],
            row["Source"],
        )
        for row in deduplicated_rows
    ]
    try:
        cursor.execute(
            """
            IF OBJECT_ID('tempdb..#EnrichedCommentsStage') IS NOT NULL
                DROP TABLE #EnrichedCommentsStage;

            CREATE TABLE #EnrichedCommentsStage (
                [CommentHash] nvarchar(64) NOT NULL PRIMARY KEY,
                [PageName] nvarchar(100) NULL,
                [PageID] nvarchar(100) NULL,
                [PostHref] nvarchar(max) NULL,
                [PostTime] datetime2(0) NULL,
                [CommentTime] datetime2(0) NULL,
                [CommentOrder] int NULL,
                [CommentLikes] int NULL,
                [MainLanguage] nvarchar(20) NULL,
                [NormalizedComment] nvarchar(max) NULL,
                [Sentiment] nvarchar(20) NULL,
                [ProcessedTime] datetime2(0) NULL,
                [Source] nvarchar(50) NULL
            )
            """
        )
        cursor.executemany(
            """
            INSERT INTO #EnrichedCommentsStage (
                [CommentHash], [PageName], [PageID], [PostHref], [PostTime], [CommentTime],
                [CommentOrder], [CommentLikes], [MainLanguage], [NormalizedComment],
                [Sentiment], [ProcessedTime], [Source]
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN target.[CommentHash] IS NULL THEN 1 ELSE 0 END) AS AddedCount,
                SUM(CASE WHEN target.[CommentHash] IS NOT NULL AND (
                    ISNULL(target.[PageName], N'') <> ISNULL(source.[PageName], N'')
                    OR ISNULL(target.[PageID], N'') <> ISNULL(source.[PageID], N'')
                    OR ISNULL(target.[PostHref], N'') <> ISNULL(source.[PostHref], N'')
                    OR ISNULL(target.[PostTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[PostTime], CONVERT(datetime2(0), '1900-01-01'))
                    OR ISNULL(target.[CommentTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[CommentTime], CONVERT(datetime2(0), '1900-01-01'))
                    OR ISNULL(target.[CommentOrder], -1) <> ISNULL(source.[CommentOrder], -1)
                    OR ISNULL(target.[CommentLikes], -1) <> ISNULL(source.[CommentLikes], -1)
                    OR ISNULL(target.[MainLanguage], N'') <> ISNULL(source.[MainLanguage], N'')
                    OR ISNULL(target.[NormalizedComment], N'') <> ISNULL(source.[NormalizedComment], N'')
                    OR ISNULL(target.[Sentiment], N'') <> ISNULL(source.[Sentiment], N'')
                    OR ISNULL(target.[Source], N'') <> ISNULL(source.[Source], N'')
                ) THEN 1 ELSE 0 END) AS UpdatedCount
            FROM #EnrichedCommentsStage AS source
            LEFT JOIN [dbo].[EnrichedComments] AS target
                ON target.[CommentHash] = source.[CommentHash]
            """
        )
        counts_row = cursor.fetchone()
        added_count = int(counts_row[0] or 0) if counts_row else 0
        updated_count = int(counts_row[1] or 0) if counts_row and len(counts_row) > 1 else 0
        if allow_updates:
            cursor.execute(
                """
                MERGE [dbo].[EnrichedComments] AS target
                USING #EnrichedCommentsStage AS source
                ON target.[CommentHash] = source.[CommentHash]
                WHEN MATCHED AND (
                    ISNULL(target.[PageName], N'') <> ISNULL(source.[PageName], N'')
                    OR ISNULL(target.[PageID], N'') <> ISNULL(source.[PageID], N'')
                    OR ISNULL(target.[PostHref], N'') <> ISNULL(source.[PostHref], N'')
                    OR ISNULL(target.[PostTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[PostTime], CONVERT(datetime2(0), '1900-01-01'))
                    OR ISNULL(target.[CommentTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[CommentTime], CONVERT(datetime2(0), '1900-01-01'))
                    OR ISNULL(target.[CommentOrder], -1) <> ISNULL(source.[CommentOrder], -1)
                    OR ISNULL(target.[CommentLikes], -1) <> ISNULL(source.[CommentLikes], -1)
                    OR ISNULL(target.[MainLanguage], N'') <> ISNULL(source.[MainLanguage], N'')
                    OR ISNULL(target.[NormalizedComment], N'') <> ISNULL(source.[NormalizedComment], N'')
                    OR ISNULL(target.[Sentiment], N'') <> ISNULL(source.[Sentiment], N'')
                    OR ISNULL(target.[Source], N'') <> ISNULL(source.[Source], N'')
                ) THEN
                    UPDATE SET
                        [PageName] = source.[PageName],
                        [PageID] = source.[PageID],
                        [PostHref] = source.[PostHref],
                        [PostTime] = source.[PostTime],
                        [CommentTime] = source.[CommentTime],
                        [CommentOrder] = source.[CommentOrder],
                        [CommentLikes] = source.[CommentLikes],
                        [MainLanguage] = source.[MainLanguage],
                        [NormalizedComment] = source.[NormalizedComment],
                        [Sentiment] = source.[Sentiment],
                        [ProcessedTime] = source.[ProcessedTime],
                        [Source] = source.[Source]
                WHEN NOT MATCHED THEN
                    INSERT (
                        [CommentHash], [PageName], [PageID], [PostHref], [PostTime],
                        [CommentTime], [CommentOrder], [CommentLikes], [MainLanguage], [NormalizedComment],
                        [Sentiment], [ProcessedTime], [Source]
                    )
                    VALUES (
                        source.[CommentHash], source.[PageName], source.[PageID], source.[PostHref], source.[PostTime],
                        source.[CommentTime], source.[CommentOrder], source.[CommentLikes], source.[MainLanguage], source.[NormalizedComment],
                        source.[Sentiment], source.[ProcessedTime], source.[Source]
                    );
                """
            )
        else:
            cursor.execute(
                """
                INSERT INTO [dbo].[EnrichedComments] (
                    [CommentHash], [PageName], [PageID], [PostHref], [PostTime],
                    [CommentTime], [CommentOrder], [CommentLikes], [MainLanguage], [NormalizedComment],
                    [Sentiment], [ProcessedTime], [Source]
                )
                SELECT
                    source.[CommentHash], source.[PageName], source.[PageID], source.[PostHref], source.[PostTime],
                    source.[CommentTime], source.[CommentOrder], source.[CommentLikes], source.[MainLanguage], source.[NormalizedComment],
                    source.[Sentiment], source.[ProcessedTime], source.[Source]
                FROM #EnrichedCommentsStage AS source
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM [dbo].[EnrichedComments] AS target
                    WHERE target.[CommentHash] = source.[CommentHash]
                )
                """
            )
            updated_count = 0
        conn.commit()
        return {"processed": len(rows), "added_count": added_count, "updated_count": updated_count}
    finally:
        try:
            cursor.execute(
                """
                IF OBJECT_ID('tempdb..#EnrichedCommentsStage') IS NOT NULL
                    DROP TABLE #EnrichedCommentsStage;
                """
            )
        except Exception:
            pass
        cursor.close()


def enrich_comments(mode="whole_db", page_name=None, page_id=None):
    if mode not in {"page_name", "page_id", "whole_db", "delta"}:
        raise ValueError("Unsupported mode. Use one of: page_name, page_id, whole_db, delta.")

    read_conn = db_connection.get_db_connection()
    write_conn = db_connection.get_db_connection()
    try:
        deleted_count = 0
        if mode in {"page_name", "page_id", "whole_db"}:
            deleted_count = clear_enriched_scope(write_conn, mode, page_name=page_name, page_id=page_id)

        models = None
        total_selected = 0
        total_processed = 0
        total_added = 0
        total_updated = 0

        for comment_rows in iter_comment_row_batches(read_conn, mode, page_name=page_name, page_id=page_id):
            if models is None:
                models = load_models()
            total_selected += len(comment_rows)
            enriched_rows = prepare_enriched_rows(comment_rows, models, source=mode)
            upsert_stats = upsert_enriched_rows(write_conn, enriched_rows, allow_updates=(mode != "delta"))
            total_processed += upsert_stats["processed"]
            total_added += upsert_stats["added_count"]
            total_updated += upsert_stats["updated_count"]

        if total_selected == 0:
            return {"selected": 0, "processed": 0, "deleted": deleted_count, "mode": mode}

        return {
            "selected": total_selected,
            "processed": total_processed,
            "added_count": total_added,
            "updated_count": total_updated,
            "deleted": deleted_count,
            "mode": mode,
            "page_name": page_name,
            "page_id": page_id,
        }
    finally:
        read_conn.close()
        write_conn.close()


def _deduplicate_rows_by_hash(rows):
    latest_by_hash = {}
    for row in rows:
        latest_by_hash[row["CommentHash"]] = row
    return latest_by_hash.values()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load comments from dbo.Comments, enrich them, and upsert into dbo.EnrichedComments.",
    )
    parser.add_argument(
        "--mode",
        choices=["page_name", "page_id", "whole_db", "delta"],
        default="whole_db",
        help="Processing scope.",
    )
    parser.add_argument("--page-name", help="Exact PageName value for page_name mode.")
    parser.add_argument("--page-id", help="Exact PageID value for page_id mode.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = enrich_comments(mode=args.mode, page_name=args.page_name, page_id=args.page_id)
    print(result)
