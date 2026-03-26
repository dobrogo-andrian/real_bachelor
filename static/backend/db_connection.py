import ctypes
import pyodbc
from flask import jsonify
from ctypes import wintypes


CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


_crypt32 = ctypes.WinDLL("Crypt32.dll")
_kernel32 = ctypes.WinDLL("Kernel32.dll")

_crypt_protect_data = _crypt32.CryptProtectData
_crypt_protect_data.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
_crypt_protect_data.restype = wintypes.BOOL

_crypt_unprotect_data = _crypt32.CryptUnprotectData
_crypt_unprotect_data.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
_crypt_unprotect_data.restype = wintypes.BOOL

_local_free = _kernel32.LocalFree
_local_free.argtypes = [wintypes.HLOCAL]
_local_free.restype = wintypes.HLOCAL


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


def _qualify_column(column_name, table_alias=None):
    if table_alias:
        return f"{table_alias}.[{column_name}]"
    return f"[{column_name}]"


def _add_in_filter_for_alias(where_clauses, params, column_name, values, table_alias=None):
    normalized_values = _normalize_filter_values(values)
    if not normalized_values:
        return normalized_values
    placeholders = ", ".join("?" for _ in normalized_values)
    where_clauses.append(f"{_qualify_column(column_name, table_alias)} IN ({placeholders})")
    params.extend(normalized_values)
    return normalized_values


def _add_first_comment_sentiment_filter(where_clauses, params, values, table_alias="EC"):
    normalized_values = _normalize_filter_values(values)
    if not normalized_values:
        return normalized_values

    placeholders = ", ".join("?" for _ in normalized_values)
    current_page_id = _qualify_column("PageID", table_alias)
    current_page_name = _qualify_column("PageName", table_alias)
    current_post_time = _qualify_column("PostTime", table_alias)

    where_clauses.append(f"""
        EXISTS (
            SELECT 1
            FROM [dbo].[EnrichedComments] AS Anchor
            WHERE
                ISNULL(Anchor.[PageID], '') = ISNULL({current_page_id}, '')
                AND ISNULL(Anchor.[PageName], '') = ISNULL({current_page_name}, '')
                AND (
                    (Anchor.[PostTime] = {current_post_time})
                    OR (Anchor.[PostTime] IS NULL AND {current_post_time} IS NULL)
                )
                AND Anchor.[Sentiment] IN ({placeholders})
                AND NOT EXISTS (
                    SELECT 1
                    FROM [dbo].[EnrichedComments] AS Earlier
                    WHERE
                        ISNULL(Earlier.[PageID], '') = ISNULL(Anchor.[PageID], '')
                        AND ISNULL(Earlier.[PageName], '') = ISNULL(Anchor.[PageName], '')
                        AND (
                            (Earlier.[PostTime] = Anchor.[PostTime])
                            OR (Earlier.[PostTime] IS NULL AND Anchor.[PostTime] IS NULL)
                        )
                        AND (
                            CASE WHEN Earlier.[CommentTime] IS NULL THEN 1 ELSE 0 END
                                < CASE WHEN Anchor.[CommentTime] IS NULL THEN 1 ELSE 0 END
                            OR (
                                CASE WHEN Earlier.[CommentTime] IS NULL THEN 1 ELSE 0 END
                                    = CASE WHEN Anchor.[CommentTime] IS NULL THEN 1 ELSE 0 END
                                AND (
                                    Earlier.[CommentTime] < Anchor.[CommentTime]
                                    OR (
                                        (
                                            (Earlier.[CommentTime] = Anchor.[CommentTime])
                                            OR (Earlier.[CommentTime] IS NULL AND Anchor.[CommentTime] IS NULL)
                                        )
                                        AND Earlier.[CommentHash] < Anchor.[CommentHash]
                                    )
                                )
                            )
                        )
                )
        )
    """)
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


def _bytes_to_blob(value):
    if not value:
        return DATA_BLOB(0, None), None
    buffer = (ctypes.c_byte * len(value))(*value)
    return DATA_BLOB(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_secret(plaintext):
    if plaintext is None:
        return None

    payload = plaintext.encode("utf-16-le")
    input_blob, input_buffer = _bytes_to_blob(payload)
    output_blob = DATA_BLOB()

    if not _crypt_protect_data(
        ctypes.byref(input_blob),
        "Comment Lab Instagram Credential",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if output_blob.pbData:
            _local_free(output_blob.pbData)


def unprotect_secret(ciphertext):
    if ciphertext is None:
        return None

    payload = bytes(ciphertext)
    input_blob, input_buffer = _bytes_to_blob(payload)
    output_blob = DATA_BLOB()
    description = wintypes.LPWSTR()

    if not _crypt_unprotect_data(
        ctypes.byref(input_blob),
        ctypes.byref(description),
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()

    try:
        plaintext_bytes = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return plaintext_bytes.decode("utf-16-le")
    finally:
        if output_blob.pbData:
            _local_free(output_blob.pbData)
        if description:
            _local_free(description)


def insert_new_user(username, email, password, instagram_login, instagram_password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM Users WHERE Username = ? OR Email = ?', (username, email))
        existing_user = cursor.fetchone()
        if existing_user:
            return jsonify({'error': 'Username or email already exists'}), 409

        encrypted_instagram_login = protect_secret(instagram_login)
        encrypted_instagram_password = protect_secret(instagram_password)

        cursor.execute('''
            INSERT INTO Users (Username, PasswordHash, Email, InstagramLoginEncrypted, InstagramPasswordEncrypted)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, password, email, pyodbc.Binary(encrypted_instagram_login), pyodbc.Binary(encrypted_instagram_password)))
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


def fetch_user_instagram_credentials(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''
            SELECT InstagramLoginEncrypted, InstagramPasswordEncrypted
            FROM Users
            WHERE Username = ?
            ''',
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "instagram_login": unprotect_secret(row[0]) if row[0] else None,
            "instagram_password": unprotect_secret(row[1]) if row[1] else None,
        }
    finally:
        cursor.close()
        conn.close()


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


def fetch_existing_post_hrefs(page_id):
    normalized_page_id = str(page_id).strip() if page_id is not None else ""
    if not normalized_page_id:
        return set()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT [PostHref]
            FROM [dbo].[Comments]
            WHERE [PageID] = ?
              AND [PostHref] IS NOT NULL
              AND LTRIM(RTRIM([PostHref])) <> ''
            """,
            (normalized_page_id,),
        )
        return {str(row[0]).strip() for row in cursor.fetchall() if row[0] and str(row[0]).strip()}
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
        dimensions["first_comment_sentiments"] = list(dimensions["sentiments"])

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

        page_names = _add_in_filter_for_alias(where_clauses, params, "PageName", filters.get("page_name"), "EC")
        page_ids = _add_in_filter_for_alias(where_clauses, params, "PageID", filters.get("page_id"), "EC")
        sources = _add_in_filter_for_alias(where_clauses, params, "Source", filters.get("source"), "EC")
        languages = _add_in_filter_for_alias(where_clauses, params, "MainLanguage", filters.get("language"), "EC")
        sentiments = _add_in_filter_for_alias(where_clauses, params, "Sentiment", filters.get("sentiment"), "EC")
        first_comment_sentiments = _add_first_comment_sentiment_filter(
            where_clauses,
            params,
            filters.get("first_comment_sentiment"),
            "EC",
        )
        text_search = (filters.get("text_search") or "").strip()
        post_time_from = (filters.get("post_time_from") or "").strip()
        post_time_to = (filters.get("post_time_to") or "").strip()
        comment_time_from = (filters.get("comment_time_from") or "").strip()
        comment_time_to = (filters.get("comment_time_to") or "").strip()
        min_likes = filters.get("min_likes")
        if post_time_from:
            where_clauses.append("EC.[PostTime] >= ?")
            params.append(post_time_from)
        if post_time_to:
            where_clauses.append("EC.[PostTime] <= ?")
            params.append(post_time_to)
        if comment_time_from:
            where_clauses.append("EC.[CommentTime] >= ?")
            params.append(comment_time_from)
        if comment_time_to:
            where_clauses.append("EC.[CommentTime] <= ?")
            params.append(comment_time_to)
        if min_likes not in (None, ""):
            where_clauses.append("ISNULL(EC.[CommentLikes], 0) >= ?")
            params.append(int(min_likes))
        if text_search:
            where_clauses.append("(EC.[Comment] LIKE ? OR EC.[FilteredComment] LIKE ?)")
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
            FROM [dbo].[EnrichedComments] AS EC
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
            FROM [dbo].[EnrichedComments] AS EC
            {where_sql}
            ORDER BY EC.[PostTime] DESC, EC.[CommentTime] DESC, EC.[CommentHash]
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
                    "first_comment_sentiment": first_comment_sentiments,
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

        _add_in_filter_for_alias(where_clauses, params, "PageName", filters.get("page_name"), "EC")
        _add_in_filter_for_alias(where_clauses, params, "PageID", filters.get("page_id"), "EC")
        _add_in_filter_for_alias(where_clauses, params, "Source", filters.get("source"), "EC")
        _add_in_filter_for_alias(where_clauses, params, "MainLanguage", filters.get("language"), "EC")
        _add_in_filter_for_alias(where_clauses, params, "Sentiment", filters.get("sentiment"), "EC")
        _add_first_comment_sentiment_filter(where_clauses, params, filters.get("first_comment_sentiment"), "EC")
        text_search = (filters.get("text_search") or "").strip()
        post_time_from = (filters.get("post_time_from") or "").strip()
        post_time_to = (filters.get("post_time_to") or "").strip()
        comment_time_from = (filters.get("comment_time_from") or "").strip()
        comment_time_to = (filters.get("comment_time_to") or "").strip()
        min_likes = filters.get("min_likes")
        if post_time_from:
            where_clauses.append("EC.[PostTime] >= ?")
            params.append(post_time_from)
        if post_time_to:
            where_clauses.append("EC.[PostTime] <= ?")
            params.append(post_time_to)
        if comment_time_from:
            where_clauses.append("EC.[CommentTime] >= ?")
            params.append(comment_time_from)
        if comment_time_to:
            where_clauses.append("EC.[CommentTime] <= ?")
            params.append(comment_time_to)
        if min_likes not in (None, ""):
            where_clauses.append("ISNULL(EC.[CommentLikes], 0) >= ?")
            params.append(int(min_likes))
        if text_search:
            where_clauses.append("(EC.[Comment] LIKE ? OR EC.[FilteredComment] LIKE ?)")
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
            FROM [dbo].[EnrichedComments] AS EC
            {where_sql}
            ORDER BY EC.[PostTime], EC.[CommentTime], EC.[CommentHash]
        """
        cursor.execute(query, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def fetch_post_anchor_sentiments(post_refs):
    normalized_refs = []
    seen = set()

    for ref in post_refs or []:
        page_id = (ref.get("page_id") or "").strip()
        page_name = (ref.get("page_name") or "").strip()
        post_time = ref.get("post_time")
        if hasattr(post_time, "isoformat"):
            post_time = post_time.isoformat(sep=" ")
        post_time = (str(post_time).strip() if post_time is not None else "")

        if not post_time:
            continue

        key = (page_id, page_name, post_time)
        if key in seen:
            continue
        seen.add(key)
        normalized_refs.append({
            "page_id": page_id,
            "page_name": page_name,
            "post_time": post_time,
        })

    if not normalized_refs:
        return {}

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        where_clauses = []
        params = []

        for ref in normalized_refs:
            if ref["page_id"]:
                where_clauses.append("([PageID] = ? AND [PostTime] = ?)")
                params.extend([ref["page_id"], ref["post_time"]])
            else:
                where_clauses.append("([PageName] = ? AND [PostTime] = ?)")
                params.extend([ref["page_name"], ref["post_time"]])

        query = f"""
            WITH RankedPostComments AS (
                SELECT
                    [PageName],
                    [PageID],
                    [PostTime],
                    [Sentiment],
                    ROW_NUMBER() OVER (
                        PARTITION BY ISNULL([PageID], ''), ISNULL([PageName], ''), [PostTime]
                        ORDER BY
                            CASE WHEN [CommentTime] IS NULL THEN 1 ELSE 0 END,
                            [CommentTime],
                            [CommentHash]
                    ) AS rn
                FROM [dbo].[EnrichedComments]
                WHERE {' OR '.join(where_clauses)}
            )
            SELECT [PageName], [PageID], [PostTime], [Sentiment]
            FROM RankedPostComments
            WHERE rn = 1
        """

        cursor.execute(query, params)
        anchors = {}
        for page_name, page_id, post_time, sentiment in cursor.fetchall():
            post_key = f"{(page_id or '').strip()}|{(page_name or '').strip()}|{post_time.isoformat(sep=' ') if hasattr(post_time, 'isoformat') else str(post_time)}"
            anchors[post_key] = (sentiment or "").strip().lower() or "unknown"
        return anchors
    finally:
        cursor.close()
        conn.close()

