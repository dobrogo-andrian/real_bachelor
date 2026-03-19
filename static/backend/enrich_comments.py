import argparse
from datetime import datetime, timezone

import pyodbc

from static.backend import db_connection
from static.backend.old_apprach.analyze_data import analyze_sentiment, load_models
from static.backend.old_apprach.process_data import (
    detect_main_language,
    filter_comment_by_main_language,
    normalize_unicode,
)


SUPPORTED_LANGUAGES = {"uk", "ru", "en", "symbols_only"}
DEFAULT_SENTIMENT = "neutral"
def build_comment_query(mode, page_name=None, page_id=None):
    base_query = """
        SELECT
            c.[CommentHash],
            c.[PageName],
            c.[PageID],
            c.[PostTime],
            c.[Comment],
            c.[CommentTime],
            c.[CommentLikes]
        FROM [dbo].[Comments] AS c
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


def enrich_comment(comment, models):
    normalized_comment = normalize_comment_payload(comment)
    main_language = detect_main_language(normalized_comment)

    if main_language not in SUPPORTED_LANGUAGES:
        main_language = "unknown"

    if main_language == "symbols_only":
        filtered_comment = normalized_comment
    elif main_language == "unknown":
        filtered_comment = normalized_comment
    else:
        filtered_comment = filter_comment_by_main_language(normalized_comment, main_language).strip()

    if not filtered_comment:
        filtered_comment = normalized_comment

    sentiment_input = filtered_comment or normalized_comment
    if sentiment_input:
        sentiment = analyze_sentiment(sentiment_input, main_language, models)
    else:
        sentiment = DEFAULT_SENTIMENT

    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = DEFAULT_SENTIMENT

    return {
        "MainLanguage": main_language,
        "FilteredComment": filtered_comment,
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

    for row in comment_rows:
        enriched = enrich_comment(row["Comment"], models)
        enriched_rows.append({
            "CommentHash": row["CommentHash"],
            "PageName": row["PageName"],
            "PageID": row["PageID"],
            "PostTime": normalize_datetime_value(row["PostTime"]),
            "Comment": row["Comment"],
            "CommentTime": normalize_datetime_value(row["CommentTime"]),
            "CommentLikes": row["CommentLikes"],
            "MainLanguage": enriched["MainLanguage"],
            "FilteredComment": enriched["FilteredComment"],
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
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
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
                ? AS [PostTime],
                ? AS [Comment],
                ? AS [CommentTime],
                ? AS [CommentLikes],
                ? AS [MainLanguage],
                ? AS [FilteredComment],
                ? AS [Sentiment],
                ? AS [ProcessedTime],
                ? AS [Source]
        ) AS source
        ON target.[CommentHash] = source.[CommentHash]
        WHEN MATCHED AND (
            ISNULL(target.[PageName], N'') <> ISNULL(source.[PageName], N'')
            OR ISNULL(target.[PageID], N'') <> ISNULL(source.[PageID], N'')
            OR ISNULL(target.[PostTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[PostTime], CONVERT(datetime2(0), '1900-01-01'))
            OR ISNULL(target.[Comment], N'') <> ISNULL(source.[Comment], N'')
            OR ISNULL(target.[CommentTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[CommentTime], CONVERT(datetime2(0), '1900-01-01'))
            OR ISNULL(target.[CommentLikes], -1) <> ISNULL(source.[CommentLikes], -1)
            OR ISNULL(target.[MainLanguage], N'') <> ISNULL(source.[MainLanguage], N'')
            OR ISNULL(target.[FilteredComment], N'') <> ISNULL(source.[FilteredComment], N'')
            OR ISNULL(target.[Sentiment], N'') <> ISNULL(source.[Sentiment], N'')
            OR ISNULL(target.[Source], N'') <> ISNULL(source.[Source], N'')
        ) THEN
            UPDATE SET
                [PageName] = source.[PageName],
                [PageID] = source.[PageID],
                [PostTime] = source.[PostTime],
                [Comment] = source.[Comment],
                [CommentTime] = source.[CommentTime],
                [CommentLikes] = source.[CommentLikes],
                [MainLanguage] = source.[MainLanguage],
                [FilteredComment] = source.[FilteredComment],
                [Sentiment] = source.[Sentiment],
                [ProcessedTime] = source.[ProcessedTime],
                [UpdateTime] = source.[ProcessedTime],
                [Source] = source.[Source]
        WHEN NOT MATCHED THEN
            INSERT (
                [CommentHash], [PageName], [PageID], [PostTime], [Comment],
                [CommentTime], [CommentLikes], [MainLanguage], [FilteredComment],
                [Sentiment], [ProcessedTime], [Source]
            )
            VALUES (
                source.[CommentHash], source.[PageName], source.[PageID], source.[PostTime], source.[Comment],
                source.[CommentTime], source.[CommentLikes], source.[MainLanguage], source.[FilteredComment],
                source.[Sentiment], source.[ProcessedTime], source.[Source]
            );
    """
    insert_if_missing_sql = """
        INSERT INTO [dbo].[EnrichedComments] (
            [CommentHash], [PageName], [PageID], [PostTime], [Comment],
            [CommentTime], [CommentLikes], [MainLanguage], [FilteredComment],
            [Sentiment], [ProcessedTime], [Source]
        )
        SELECT
            source.[CommentHash], source.[PageName], source.[PageID], source.[PostTime], source.[Comment],
            source.[CommentTime], source.[CommentLikes], source.[MainLanguage], source.[FilteredComment],
            source.[Sentiment], source.[ProcessedTime], source.[Source]
        FROM (
            SELECT
                ? AS [CommentHash],
                ? AS [PageName],
                ? AS [PageID],
                ? AS [PostTime],
                ? AS [Comment],
                ? AS [CommentTime],
                ? AS [CommentLikes],
                ? AS [MainLanguage],
                ? AS [FilteredComment],
                ? AS [Sentiment],
                ? AS [ProcessedTime],
                ? AS [Source]
        ) AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM [dbo].[EnrichedComments] AS target
            WHERE target.[CommentHash] = source.[CommentHash]
        );
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
                row["PostTime"],
                row["Comment"],
                row["CommentTime"],
                row["CommentLikes"],
                row["MainLanguage"],
                row["FilteredComment"],
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
