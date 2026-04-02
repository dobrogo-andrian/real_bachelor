import os
import hashlib
import re
from datetime import datetime, timezone

import pandas as pd
import pyodbc

from static.backend.common_utils import extract_sort_key
from static.backend import db_connection


REQUIRED_COLUMNS = ("Comment", "Time", "Likes")
DEFAULT_MAX_BATCH_ROWS = 500


def validate_columns(df):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def derive_page_id(filename):
    match = re.match(r"(.+)_\d+\.csv$", filename, re.IGNORECASE)
    if match:
        return match.group(1)
    return os.path.splitext(filename)[0]


def normalize_hash_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="seconds")
    return str(value).strip()


def compute_comment_hash(page_id, post_href, comment_time, comment):
    base = "|".join([
        normalize_hash_value(page_id),
        normalize_hash_value(post_href),
        normalize_hash_value(comment_time),
        normalize_hash_value(comment),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def prepare_rows(df, page_id, post_href, post_time, load_time):
    validate_columns(df)
    rows = []
    for row in df.itertuples(index=False):
        comment_time = pd.to_datetime(row.Time, errors="coerce")
        comment_time_value = comment_time.to_pydatetime() if pd.notna(comment_time) else None
        comment_value = str(row.Comment)
        page_name = getattr(row, "PageName", None)
        row_page_id = getattr(row, "PageID", None)
        if page_name is None or str(page_name).strip() == "":
            page_name = "unknown"
        if row_page_id is None or str(row_page_id).strip() == "":
            row_page_id = page_id
        rows.append({
            "CommentHash": compute_comment_hash(row_page_id, post_href, comment_time_value, comment_value),
            "PageName": page_name,
            "PageID": row_page_id,
            "PostHref": post_href,
            "PostTime": post_time,
            "Comment": comment_value,
            "CommentTime": comment_time_value,
            "CommentLikes": int(row.Likes) if str(row.Likes).strip() else 0,
            "LoadTime": load_time,
        })
    return rows


def prepare_rows_from_comment_records(comment_records, page_id, post_href, page_name=None, load_time=None, post_time=None):
    resolved_page_name = str(page_name or "").strip() or "unknown"
    resolved_load_time = load_time or datetime.now(timezone.utc).replace(tzinfo=None)
    resolved_post_time = post_time
    rows = []

    for raw_comment, raw_time, raw_likes in comment_records:
        comment_time = pd.to_datetime(raw_time, errors="coerce")
        comment_time_value = comment_time.to_pydatetime() if pd.notna(comment_time) else None
        if resolved_post_time is None and comment_time_value is not None:
            resolved_post_time = comment_time_value

        comment_value = "" if raw_comment is None else str(raw_comment)
        likes_value = int(raw_likes) if str(raw_likes).strip() else 0
        rows.append(
            {
                "CommentHash": compute_comment_hash(page_id, post_href, comment_time_value, comment_value),
                "PageName": resolved_page_name,
                "PageID": page_id,
                "PostHref": post_href,
                "PostTime": None,
                "Comment": comment_value,
                "CommentTime": comment_time_value,
                "CommentLikes": likes_value,
                "LoadTime": resolved_load_time,
            }
        )

    for row in rows:
        row["PostTime"] = resolved_post_time
    return rows


def insert_rows(conn, rows):
    if not rows:
        return 0

    cursor = conn.cursor()
    cursor.fast_executemany = True
    cursor.setinputsizes([
        (pyodbc.SQL_WVARCHAR, 64, 0),
        (pyodbc.SQL_WVARCHAR, 100, 0),
        (pyodbc.SQL_WVARCHAR, 100, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_INTEGER, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
    ])
    deduplicated_rows = list(_deduplicate_rows_by_hash(rows))
    params = [
        (
            r["CommentHash"],
            r["PageName"],
            r["PageID"],
            r["PostHref"],
            r["PostTime"],
            r["Comment"],
            r["CommentTime"],
            r["CommentLikes"],
            r["LoadTime"],
        )
        for r in deduplicated_rows
    ]
    try:
        cursor.execute(
            """
            IF OBJECT_ID('tempdb..#CommentsStage') IS NOT NULL
                DROP TABLE #CommentsStage;

            CREATE TABLE #CommentsStage (
                [CommentHash] nvarchar(64) NOT NULL PRIMARY KEY,
                [PageName] nvarchar(100) NULL,
                [PageID] nvarchar(100) NULL,
                [PostHref] nvarchar(max) NULL,
                [PostTime] datetime2(0) NULL,
                [Comment] nvarchar(max) NULL,
                [CommentTime] datetime2(0) NULL,
                [CommentLikes] int NULL,
                [LoadTime] datetime2(0) NULL
            )
            """
        )
        cursor.executemany(
            """
            INSERT INTO #CommentsStage (
                [CommentHash], [PageName], [PageID], [PostHref], [PostTime],
                [Comment], [CommentTime], [CommentLikes], [LoadTime]
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        cursor.execute(
            """
            MERGE [dbo].[Comments] AS target
            USING #CommentsStage AS source
            ON target.[CommentHash] = source.[CommentHash]
            WHEN MATCHED AND (
                ISNULL(target.[PageName], N'') <> ISNULL(source.[PageName], N'')
                OR ISNULL(target.[PageID], N'') <> ISNULL(source.[PageID], N'')
                OR ISNULL(target.[PostHref], N'') <> ISNULL(source.[PostHref], N'')
                OR ISNULL(target.[PostTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[PostTime], CONVERT(datetime2(0), '1900-01-01'))
                OR ISNULL(target.[Comment], N'') <> ISNULL(source.[Comment], N'')
                OR ISNULL(target.[CommentTime], CONVERT(datetime2(0), '1900-01-01')) <> ISNULL(source.[CommentTime], CONVERT(datetime2(0), '1900-01-01'))
                OR ISNULL(target.[CommentLikes], -1) <> ISNULL(source.[CommentLikes], -1)
            ) THEN
                UPDATE SET
                    [PageName] = source.[PageName],
                    [PageID] = source.[PageID],
                    [PostHref] = source.[PostHref],
                    [PostTime] = source.[PostTime],
                    [Comment] = source.[Comment],
                    [CommentTime] = source.[CommentTime],
                    [CommentLikes] = source.[CommentLikes],
                    [LoadTime] = source.[LoadTime]
            WHEN NOT MATCHED THEN
                INSERT (
                    [CommentHash], [PageName], [PageID], [PostHref], [PostTime], [Comment], [CommentTime], [CommentLikes], [LoadTime]
                )
                VALUES (
                    source.[CommentHash], source.[PageName], source.[PageID], source.[PostHref], source.[PostTime], source.[Comment], source.[CommentTime], source.[CommentLikes], source.[LoadTime]
                );
            """
        )
        conn.commit()
        return len(rows)
    finally:
        try:
            cursor.execute(
                """
                IF OBJECT_ID('tempdb..#CommentsStage') IS NOT NULL
                    DROP TABLE #CommentsStage;
                """
            )
        except Exception:
            pass
        cursor.close()


def _deduplicate_rows_by_hash(rows):
    latest_by_hash = {}
    for row in rows:
        latest_by_hash[row["CommentHash"]] = row
    return latest_by_hash.values()


def iter_row_chunks(rows, chunk_size=DEFAULT_MAX_BATCH_ROWS):
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    for index in range(0, len(rows), chunk_size):
        yield rows[index:index + chunk_size]


def load_row_batches(row_batches, dry_run=True, conn=None, chunk_size=DEFAULT_MAX_BATCH_ROWS):
    own_connection = conn is None and not dry_run
    active_connection = conn
    if own_connection:
        active_connection = db_connection.get_db_connection()

    input_batches_found = 0
    processed_chunks = 0
    loaded_rows = 0

    try:
        for batch in row_batches:
            if not batch:
                continue

            input_batches_found += 1
            for chunk in iter_row_chunks(batch, chunk_size=chunk_size):
                processed_chunks += 1
                if dry_run:
                    loaded_rows += len(chunk)
                    continue

                loaded_rows += insert_rows(active_connection, chunk)
        return {
            "files_processed": input_batches_found,
            "rows_loaded": loaded_rows,
            "input_files_found": input_batches_found,
            "dry_run": dry_run,
            "batches_processed": input_batches_found,
            "chunks_processed": processed_chunks,
        }
    finally:
        if own_connection and active_connection is not None:
            active_connection.close()


def iter_csv_files(input_folder):
    for root, _, files in os.walk(input_folder):
        for fname in files:
            if fname.lower().endswith(".csv"):
                yield os.path.join(root, fname)


def load_to_db(input_folder, dry_run=True):
    if not input_folder:
        raise ValueError("input_folder is required")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    input_dir = input_folder
    if not os.path.isabs(input_dir):
        input_dir = os.path.join(base_dir, input_dir)

    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"Input folder not found: {input_dir}")

    input_files = sorted(
        iter_csv_files(input_dir),
        key=lambda p: (os.path.dirname(p), extract_sort_key(os.path.basename(p))),
    )
    print(f"[INFO] load_to_db: input_dir={input_dir}, files={len(input_files)}, dry_run={dry_run}")
    for path in input_files:
        print(f"[INFO] load_to_db: found file {path}")
    if not input_files:
        raise FileNotFoundError(f"No CSV files found under: {input_dir}")

    def row_batches():
        for input_csv_path in input_files:
            filename = os.path.basename(input_csv_path)
            page_id = derive_page_id(filename)

            df = pd.read_csv(input_csv_path)
            validate_columns(df)

            post_href_series = df["PostHref"] if "PostHref" in df.columns else pd.Series(dtype="object")
            post_href = str(post_href_series.dropna().iloc[0]).strip() if not post_href_series.dropna().empty else None
            time_series = pd.to_datetime(df["Time"], errors="coerce")
            post_time = time_series.dropna().iloc[0].to_pydatetime() if not time_series.dropna().empty else None
            load_time = datetime.now(timezone.utc).replace(tzinfo=None)

            rows = prepare_rows(df, page_id, post_href, post_time, load_time)
            print(f"[{'DRY RUN' if dry_run else 'INFO'}] Prepared {len(rows)} rows from {input_csv_path}")
            yield rows

    return load_row_batches(row_batches(), dry_run=dry_run)


if __name__ == "__main__":
    input_folder = os.getenv("INPUT_FOLDER")
    if not input_folder:
        raise ValueError("Set INPUT_FOLDER before running load_to_db.py directly.")
    load_to_db(input_folder=input_folder)
