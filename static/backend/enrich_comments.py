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


def analyze_sentiment(comment, classifier):
    try:
        result = classifier(comment)
        label = str(result[0]["label"]).lower()
        if label in {"label_0", "negative"}:
            return "negative"
        if label in {"label_1", "neutral"}:
            return "neutral"
        if label in {"label_2", "positive"}:
            return "positive"
    except Exception:
        return DEFAULT_SENTIMENT

    return DEFAULT_SENTIMENT


def build_comment_query(mode, page_name=None, page_id=None):
    base_query = """
                 SELECT c.[CommentHash],
                        c.[PageName],
                        c.[PageID],
                        c.[PostHref],
                        c.[PostTime],
                        c.[Comment],
                        c.[CommentTime],
                        c.[CommentLikes]
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


def enrich_comment(comment, models):
    normalized_comment = normalize_comment_payload(comment)
    normalized_analysis_comment = normalize_comment_for_analysis(normalized_comment)
    main_language = detect_main_language(normalized_comment)

    if main_language not in SUPPORTED_LANGUAGES:
        main_language = "other"

    if normalized_analysis_comment:
        sentiment = analyze_sentiment(normalized_analysis_comment, models)
    else:
        sentiment = DEFAULT_SENTIMENT

    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = DEFAULT_SENTIMENT

    return {
        "MainLanguage": main_language,
        "NormalizedComment": normalized_analysis_comment,
        "Sentiment": sentiment,
    }


def fetch_comment_rows(conn, mode, page_name=None, page_id=None):
    query, params = build_comment_query(mode, page_name=page_name, page_id=page_id)
    cursor = conn.cursor()
    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]

    rows = []
    for raw_row in cursor.fetchall():
        rows.append(dict(zip(columns, raw_row)))

    cursor.close()
    return rows


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
    comment_order_by_hash = assign_comment_order(comment_rows)

    for row in comment_rows:
        enriched = enrich_comment(row["Comment"], models)
        comment_order = comment_order_by_hash.get(row["CommentHash"])
        enriched_rows.append({
            "CommentHash": row["CommentHash"],
            "PageName": row["PageName"],
            "PageID": row["PageID"],
            "PostHref": row.get("PostHref"),
            "PostTime": normalize_datetime_value(row["PostTime"]),
            "CommentTime": normalize_datetime_value(row["CommentTime"]),
            "CommentOrder": comment_order,
            "CommentLikes": 0 if comment_order == 1 else row["CommentLikes"],
            "MainLanguage": enriched["MainLanguage"],
            "NormalizedComment": enriched["NormalizedComment"],
            "Sentiment": enriched["Sentiment"],
            "ProcessedTime": processed_time,
            "Source": source,
        })

    return enriched_rows


def upsert_enriched_rows(conn, rows, allow_updates=True):
    if not rows:
        return {"processed": 0, "added_count": 0, "updated_count": 0}

    cursor = conn.cursor()
    added_count = 0
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
    merge_sql = """
        MERGE [dbo].[EnrichedComments] AS target
        USING (
            SELECT
                ? AS [CommentHash],
                ? AS [PageName],
                ? AS [PageID],
                ? AS [PostHref],
                ? AS [PostTime],
                ? AS [CommentTime],
                ? AS [CommentOrder],
                ? AS [CommentLikes],
                ? AS [MainLanguage],
                ? AS [NormalizedComment],
                ? AS [Sentiment],
                ? AS [ProcessedTime],
                ? AS [Source]
        ) AS source
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
    insert_if_missing_sql = """
                            INSERT INTO [dbo].[EnrichedComments] ([CommentHash], [PageName], [PageID], [PostHref],
                                                                  [PostTime],
                                                                  [CommentTime], [CommentOrder], [CommentLikes],
                                                                  [MainLanguage], [NormalizedComment],
                                                                  [Sentiment], [ProcessedTime], [Source])
                            SELECT source.[CommentHash],
                                   source.[PageName],
                                   source.[PageID],
                                   source.[PostHref],
                                   source.[PostTime],
                                   source.[CommentTime],
                                   source.[CommentOrder],
                                   source.[CommentLikes],
                                   source.[MainLanguage],
                                   source.[NormalizedComment],
                                   source.[Sentiment],
                                   source.[ProcessedTime],
                                   source.[Source]
                            FROM (SELECT ? AS [CommentHash],
                                         ? AS [PageName],
                                         ? AS [PageID],
                                         ? AS [PostHref],
                                         ? AS [PostTime],
                                         ? AS [CommentTime],
                                         ? AS [CommentOrder],
                                         ? AS [CommentLikes],
                                         ? AS [MainLanguage],
                                         ? AS [NormalizedComment],
                                         ? AS [Sentiment],
                                         ? AS [ProcessedTime],
                                         ? AS [Source]) AS source
                            WHERE NOT EXISTS (SELECT 1
                                              FROM [dbo].[EnrichedComments] AS target
                                              WHERE target.[CommentHash] = source.[CommentHash]); \
                            """
    updated_count = 0
    for row in rows:
        cursor.execute(
            "SELECT COUNT(1) FROM [dbo].[EnrichedComments] WHERE [CommentHash] = ?",
            row["CommentHash"],
        )
        existed_before = cursor.fetchone()[0] > 0
        cursor.execute(
            merge_sql if allow_updates else insert_if_missing_sql,
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
            ),
        )
        if not existed_before and cursor.rowcount > 0:
            added_count += 1
        elif existed_before and allow_updates and cursor.rowcount > 0:
            updated_count += 1
    conn.commit()
    cursor.close()
    return {"processed": len(rows), "added_count": added_count, "updated_count": updated_count}


def enrich_comments(mode="whole_db", page_name=None, page_id=None):
    if mode not in {"page_name", "page_id", "whole_db", "delta"}:
        raise ValueError("Unsupported mode. Use one of: page_name, page_id, whole_db, delta.")

    conn = db_connection.get_db_connection()
    try:
        deleted_count = 0
        if mode in {"page_name", "page_id", "whole_db"}:
            deleted_count = clear_enriched_scope(conn, mode, page_name=page_name, page_id=page_id)

        comment_rows = fetch_comment_rows(conn, mode, page_name=page_name, page_id=page_id)
        if not comment_rows:
            return {"selected": 0, "processed": 0, "deleted": deleted_count, "mode": mode}

        models = load_models()
        enriched_rows = prepare_enriched_rows(comment_rows, models, source=mode)
        upsert_stats = upsert_enriched_rows(conn, enriched_rows, allow_updates=(mode != "delta"))
        return {
            "selected": len(comment_rows),
            "processed": upsert_stats["processed"],
            "added_count": upsert_stats["added_count"],
            "updated_count": upsert_stats["updated_count"],
            "deleted": deleted_count,
            "mode": mode,
            "page_name": page_name,
            "page_id": page_id,
        }
    finally:
        conn.close()


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
