import os
import re
import hashlib
from datetime import datetime, timezone

import pandas as pd
import pyodbc

from static.backend.common_utils import extract_sort_key
from static.backend import db_connection


REQUIRED_COLUMNS = ("Comment", "Time", "Likes")


def validate_columns(df):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def parse_post_number(filename):
    match = re.search(r"_(\d+)\.csv$", filename)
    return int(match.group(1)) if match else None


def compute_comment_hash(page_id, post_time, row_index):
    base = f"{page_id}|{post_time or ''}|{row_index}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def prepare_rows(df, page_id, post_number, post_time, load_time):
    validate_columns(df)
    rows = []
    for idx, row in enumerate(df.itertuples(index=False), start=1):
        comment_time = pd.to_datetime(row.Time, errors="coerce")
        rows.append({
            "CommentHash": compute_comment_hash(page_id, post_time, idx),
            "PageName": "unknown",
            "PageID": page_id,
            "PostTime": post_time,
            "PostNumber": post_number,
            "Comment": str(row.Comment),
            "CommentTime": comment_time.to_pydatetime() if pd.notna(comment_time) else None,
            "CommentLikes": int(row.Likes) if str(row.Likes).strip() else 0,
            "LoadTime": load_time,
            "Source": "Web interface",
        })
    return rows


def insert_rows(conn, rows):
    if not rows:
        return

    cursor = conn.cursor()
    cursor.fast_executemany = True
    cursor.setinputsizes([
        (pyodbc.SQL_WVARCHAR, 64, 0),
        (pyodbc.SQL_WVARCHAR, 100, 0),
        (pyodbc.SQL_WVARCHAR, 100, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_INTEGER, 0, 0),
        (pyodbc.SQL_WVARCHAR, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_INTEGER, 0, 0),
        (pyodbc.SQL_TYPE_TIMESTAMP, 0, 0),
        (pyodbc.SQL_WVARCHAR, 50, 0),
    ])
    cursor.executemany(
        """
        MERGE [dbo].[Comments] AS target
        USING (
            SELECT
                ? AS [CommentHash],
                ? AS [PageName],
                ? AS [PageID],
                ? AS [PostTime],
                ? AS [PostNumber],
                ? AS [Comment],
                ? AS [CommentTime],
                ? AS [CommentLikes],
                ? AS [LoadTime],
                ? AS [Source]
        ) AS source
        ON target.[CommentHash] = source.[CommentHash]
        WHEN MATCHED THEN
            UPDATE SET
                [PageName] = source.[PageName],
                [PageID] = source.[PageID],
                [PostTime] = source.[PostTime],
                [PostNumber] = source.[PostNumber],
                [Comment] = source.[Comment],
                [CommentTime] = source.[CommentTime],
                [CommentLikes] = source.[CommentLikes],
                [LoadTime] = source.[LoadTime],
                [Source] = source.[Source]
        WHEN NOT MATCHED THEN
            INSERT (
                [CommentHash], [PageName], [PageID], [PostTime], [PostNumber],
                [Comment], [CommentTime], [CommentLikes], [LoadTime], [Source]
            )
            VALUES (
                source.[CommentHash], source.[PageName], source.[PageID], source.[PostTime], source.[PostNumber],
                source.[Comment], source.[CommentTime], source.[CommentLikes], source.[LoadTime], source.[Source]
            );
        """,
        [
            (
                r["CommentHash"],
                r["PageName"],
                r["PageID"],
                r["PostTime"],
                r["PostNumber"],
                r["Comment"],
                r["CommentTime"],
                r["CommentLikes"],
                r["LoadTime"],
                r["Source"],
            )
            for r in rows
        ],
    )
    conn.commit()


def iter_csv_files(input_folder):
    for root, _, files in os.walk(input_folder):
        for fname in files:
            if fname.lower().endswith(".csv"):
                yield os.path.join(root, fname)


def load_to_db(input_folder="unprocessed_data", dry_run=True):
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

    conn = None
    if not dry_run:
        conn = db_connection.get_db_connection()

    try:
        for input_csv_path in input_files:
            filename = os.path.basename(input_csv_path)
            page_id = filename
            post_number = parse_post_number(filename)

            df = pd.read_csv(input_csv_path)
            validate_columns(df)

            time_series = pd.to_datetime(df["Time"], errors="coerce")
            post_time = time_series.dropna().iloc[0].to_pydatetime() if not time_series.dropna().empty else None
            load_time = datetime.now(timezone.utc).replace(tzinfo=None)

            rows = prepare_rows(df, page_id, post_number, post_time, load_time)

            if dry_run:
                print(f"[DRY RUN] Prepared {len(rows)} rows from {input_csv_path}")
                continue

            insert_rows(conn, rows)
            print(f"[INFO] Inserted {len(rows)} rows from {input_csv_path}")
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    load_to_db()
