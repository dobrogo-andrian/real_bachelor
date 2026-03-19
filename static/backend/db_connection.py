import pyodbc
from flask import jsonify


def _normalize_filter_values(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = [value]
    normalized = []
    for item in raw_values:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _add_in_filter(where_clauses, params, column_name, values):
    normalized_values = _normalize_filter_values(values)
    if not normalized_values:
        return normalized_values
    placeholders = ", ".join("?" for _ in normalized_values)
    where_clauses.append(f"[{column_name}] IN ({placeholders})")
    params.extend(normalized_values)
    return normalized_values


def get_db_connection():
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=localhost;'
        'DATABASE=social-media-optimizer;'
        'UID=social-media-optimizer;'
        'PWD=social-media-optimizer'
    )
    return conn


def insert_new_user(username, email, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Users WHERE Username = ? OR Email = ?', (username, email))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'error': 'Username or email already exists'}), 409

        cursor.execute('''
            INSERT INTO Users (Username, PasswordHash, Email)
            VALUES (?, ?, ?)
        ''', (username, password, email))
        conn.commit()

        return jsonify({'message': 'User created successfully', 'redirect': '/login'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()



def fetch_user(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT PasswordHash FROM Users WHERE Username = ?', (username,))
    return cursor.fetchone()


def fetch_distinct_comment_dimensions():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT [PageName]
            FROM [dbo].[Comments]
            WHERE [PageName] IS NOT NULL AND LTRIM(RTRIM([PageName])) <> ''
            ORDER BY [PageName]
        """)
        page_names = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT [PageID]
            FROM [dbo].[Comments]
            WHERE [PageID] IS NOT NULL AND LTRIM(RTRIM([PageID])) <> ''
            ORDER BY [PageID]
        """)
        page_ids = [row[0] for row in cursor.fetchall()]

        return {
            "page_names": page_names,
            "page_ids": page_ids,
        }
    finally:
        cursor.close()
        conn.close()


def fetch_advanced_comment_dimensions():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        dimensions = {}

        cursor.execute("""
            SELECT DISTINCT [PageName]
            FROM [dbo].[EnrichedComments]
            WHERE [PageName] IS NOT NULL AND LTRIM(RTRIM([PageName])) <> ''
            ORDER BY [PageName]
        """)
        dimensions["page_names"] = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT [PageID]
            FROM [dbo].[EnrichedComments]
            WHERE [PageID] IS NOT NULL AND LTRIM(RTRIM([PageID])) <> ''
            ORDER BY [PageID]
        """)
        dimensions["page_ids"] = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT [Source]
            FROM [dbo].[EnrichedComments]
            WHERE [Source] IS NOT NULL AND LTRIM(RTRIM([Source])) <> ''
            ORDER BY [Source]
        """)
        dimensions["sources"] = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT [MainLanguage]
            FROM [dbo].[EnrichedComments]
            WHERE [MainLanguage] IS NOT NULL AND LTRIM(RTRIM([MainLanguage])) <> ''
            ORDER BY [MainLanguage]
        """)
        dimensions["languages"] = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT [Sentiment]
            FROM [dbo].[EnrichedComments]
            WHERE [Sentiment] IS NOT NULL AND LTRIM(RTRIM([Sentiment])) <> ''
            ORDER BY [Sentiment]
        """)
        dimensions["sentiments"] = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT
                MIN([PostTime]) AS MinPostTime,
                MAX([PostTime]) AS MaxPostTime,
                MIN([CommentTime]) AS MinCommentTime,
                MAX([CommentTime]) AS MaxCommentTime,
                MIN([CommentLikes]) AS MinCommentLikes,
                MAX([CommentLikes]) AS MaxCommentLikes
            FROM [dbo].[EnrichedComments]
        """)
        range_row = cursor.fetchone()
        dimensions["ranges"] = {
            "min_post_time": range_row[0].isoformat(sep=" ") if range_row and range_row[0] else None,
            "max_post_time": range_row[1].isoformat(sep=" ") if range_row and range_row[1] else None,
            "min_comment_time": range_row[2].isoformat(sep=" ") if range_row and range_row[2] else None,
            "max_comment_time": range_row[3].isoformat(sep=" ") if range_row and range_row[3] else None,
            "min_comment_likes": int(range_row[4]) if range_row and range_row[4] is not None else 0,
            "max_comment_likes": int(range_row[5]) if range_row and range_row[5] is not None else 0,
        }

        return dimensions
    finally:
        cursor.close()
        conn.close()


def fetch_enriched_comment_preview(filters, limit=100):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []

        page_names = _add_in_filter(where_clauses, params, "PageName", filters.get("page_name"))
        page_ids = _add_in_filter(where_clauses, params, "PageID", filters.get("page_id"))
        sources = _add_in_filter(where_clauses, params, "Source", filters.get("source"))
        languages = _add_in_filter(where_clauses, params, "MainLanguage", filters.get("language"))
        sentiments = _add_in_filter(where_clauses, params, "Sentiment", filters.get("sentiment"))
        text_search = (filters.get("text_search") or "").strip()
        post_time_from = (filters.get("post_time_from") or "").strip()
        post_time_to = (filters.get("post_time_to") or "").strip()
        comment_time_from = (filters.get("comment_time_from") or "").strip()
        comment_time_to = (filters.get("comment_time_to") or "").strip()
        min_likes = filters.get("min_likes")
        if post_time_from:
            where_clauses.append("[PostTime] >= ?")
            params.append(post_time_from)
        if post_time_to:
            where_clauses.append("[PostTime] <= ?")
            params.append(post_time_to)
        if comment_time_from:
            where_clauses.append("[CommentTime] >= ?")
            params.append(comment_time_from)
        if comment_time_to:
            where_clauses.append("[CommentTime] <= ?")
            params.append(comment_time_to)
        if min_likes not in (None, ""):
            where_clauses.append("ISNULL([CommentLikes], 0) >= ?")
            params.append(int(min_likes))
        if text_search:
            where_clauses.append("([Comment] LIKE ? OR [FilteredComment] LIKE ?)")
            like_pattern = f"%{text_search}%"
            params.extend([like_pattern, like_pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        summary_query = f"""
            SELECT
                COUNT(*) AS TotalComments,
                COUNT(DISTINCT [CommentHash]) AS DistinctComments,
                COUNT(DISTINCT CONCAT(CONVERT(varchar(19), [PostTime], 120), '|', ISNULL([PageID], ''))) AS DistinctPosts,
                COUNT(DISTINCT [PageID]) AS DistinctPages,
                AVG(CAST(ISNULL([CommentLikes], 0) AS FLOAT)) AS AverageLikes,
                MAX([ProcessedTime]) AS LatestProcessedTime
            FROM [dbo].[EnrichedComments]
            {where_sql}
        """
        cursor.execute(summary_query, params)
        summary_row = cursor.fetchone()

        preview_query = f"""
            SELECT TOP (?)
                [CommentHash],
                [PageName],
                [PageID],
                [PostTime],
                [Comment],
                [CommentTime],
                [CommentLikes],
                [MainLanguage],
                [FilteredComment],
                [Sentiment],
                [ProcessedTime],
                [UpdateTime],
                [Source]
            FROM [dbo].[EnrichedComments]
            {where_sql}
            ORDER BY [PostTime] DESC, [CommentTime] DESC, [CommentHash]
        """
        cursor.execute(preview_query, [int(limit)] + params)
        columns = [column[0] for column in cursor.description]
        rows = []
        for raw_row in cursor.fetchall():
            row = dict(zip(columns, raw_row))
            for key, value in list(row.items()):
                if hasattr(value, "isoformat"):
                    row[key] = value.isoformat(sep=" ")
            rows.append(row)

        return {
            "summary": {
                "total_comments": int(summary_row[0]) if summary_row and summary_row[0] is not None else 0,
                "distinct_comments": int(summary_row[1]) if summary_row and summary_row[1] is not None else 0,
                "distinct_posts": int(summary_row[2]) if summary_row and summary_row[2] is not None else 0,
                "distinct_pages": int(summary_row[3]) if summary_row and summary_row[3] is not None else 0,
                "average_likes": round(float(summary_row[4]), 2) if summary_row and summary_row[4] is not None else 0.0,
                "latest_processed_time": summary_row[5].isoformat(sep=" ") if summary_row and summary_row[5] else None,
            },
            "rows": rows,
            "applied_filters": {
                key: value for key, value in {
                    "page_name": page_names,
                    "page_id": page_ids,
                    "source": sources,
                    "language": languages,
                    "sentiment": sentiments,
                    "post_time_from": post_time_from,
                    "post_time_to": post_time_to,
                    "comment_time_from": comment_time_from,
                    "comment_time_to": comment_time_to,
                    "min_likes": min_likes,
                    "text_search": text_search,
                }.items() if value not in (None, "", [])
            },
        }
    finally:
        cursor.close()
        conn.close()


def fetch_enriched_comment_rows(filters):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []

        _add_in_filter(where_clauses, params, "PageName", filters.get("page_name"))
        _add_in_filter(where_clauses, params, "PageID", filters.get("page_id"))
        _add_in_filter(where_clauses, params, "Source", filters.get("source"))
        _add_in_filter(where_clauses, params, "MainLanguage", filters.get("language"))
        _add_in_filter(where_clauses, params, "Sentiment", filters.get("sentiment"))
        text_search = (filters.get("text_search") or "").strip()
        post_time_from = (filters.get("post_time_from") or "").strip()
        post_time_to = (filters.get("post_time_to") or "").strip()
        comment_time_from = (filters.get("comment_time_from") or "").strip()
        comment_time_to = (filters.get("comment_time_to") or "").strip()
        min_likes = filters.get("min_likes")
        if post_time_from:
            where_clauses.append("[PostTime] >= ?")
            params.append(post_time_from)
        if post_time_to:
            where_clauses.append("[PostTime] <= ?")
            params.append(post_time_to)
        if comment_time_from:
            where_clauses.append("[CommentTime] >= ?")
            params.append(comment_time_from)
        if comment_time_to:
            where_clauses.append("[CommentTime] <= ?")
            params.append(comment_time_to)
        if min_likes not in (None, ""):
            where_clauses.append("ISNULL([CommentLikes], 0) >= ?")
            params.append(int(min_likes))
        if text_search:
            where_clauses.append("([Comment] LIKE ? OR [FilteredComment] LIKE ?)")
            like_pattern = f"%{text_search}%"
            params.extend([like_pattern, like_pattern])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
            SELECT
                [CommentHash],
                [PageName],
                [PageID],
                [PostTime],
                [Comment],
                [CommentTime],
                [CommentLikes],
                [MainLanguage],
                [FilteredComment],
                [Sentiment],
                [ProcessedTime],
                [UpdateTime],
                [Source]
            FROM [dbo].[EnrichedComments]
            {where_sql}
            ORDER BY [PostTime], [CommentTime], [CommentHash]
        """
        cursor.execute(query, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()

