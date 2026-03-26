from collections import Counter, defaultdict
from datetime import datetime

from static.backend import db_connection


SENTIMENT_ORDER = ["positive", "neutral", "negative"]


def _normalize_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _build_post_key(page_id, page_name, post_time):
    normalized_post_time = _normalize_datetime(post_time)
    if normalized_post_time:
        post_time_value = normalized_post_time.isoformat(sep=" ")
    else:
        post_time_value = _normalize_text(post_time)
    return f"{_normalize_text(page_id)}|{_normalize_text(page_name)}|{post_time_value}"


def _safe_percentage(part, total):
    if not total:
        return 0.0
    return round((part / total) * 100, 2)


def _safe_average(values):
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _compute_percentile(sorted_values, percentile):
    if not sorted_values:
        return 0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = rank - lower_index
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + (upper_value - lower_value) * weight


def _build_adaptive_histogram_bins(lengths):
    if not lengths:
        return []

    sorted_lengths = sorted(int(length) for length in lengths)
    max_length = sorted_lengths[-1]

    # Keep dense short-comment zones readable, then widen bins into the tail.
    base_edges = [0, 1, 2, 3, 4, 5, 7, 10, 15, 20]
    percentile_edges = [
        int(round(_compute_percentile(sorted_lengths, 0.75))),
        int(round(_compute_percentile(sorted_lengths, 0.90))),
        int(round(_compute_percentile(sorted_lengths, 0.95))),
        int(round(_compute_percentile(sorted_lengths, 0.99))),
    ]

    candidate_edges = sorted(set(edge for edge in (base_edges + percentile_edges) if 0 <= edge < max_length))
    if not candidate_edges or candidate_edges[0] != 0:
        candidate_edges = [0] + candidate_edges

    bins = []
    for index, start in enumerate(candidate_edges):
        next_edge = candidate_edges[index + 1] if index + 1 < len(candidate_edges) else None
        end = (next_edge - 1) if next_edge is not None else max_length
        if end < start:
            continue
        count = sum(1 for length in sorted_lengths if start <= length <= end)
        bins.append({
            "label": f"{start}-{end}" if next_edge is not None else f"{start}+",
            "value": count,
            "sort_start": start,
        })

    return [bucket for bucket in bins if bucket["value"] > 0]


def fetch_enriched_comments_for_page(selection_type, selection_value):
    if selection_type not in {"page_name", "page_id"}:
        raise ValueError("selection_type must be `page_name` or `page_id`.")
    if not selection_value:
        raise ValueError("selection_value is required.")

    filter_column = "PageName" if selection_type == "page_name" else "PageID"
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
            [Source]
        FROM [dbo].[EnrichedComments]
        WHERE [{filter_column}] = ?
        ORDER BY [PostTime], [CommentTime], [CommentHash]
    """

    conn = db_connection.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query, selection_value)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _build_chart_visibility(filters, rows, language_counts, sentiment_counts, ordered_posts):
    distinct_pages = len({
        _normalize_text(row.get("PageID")) or _normalize_text(row.get("PageName"))
        for row in rows
        if _normalize_text(row.get("PageID")) or _normalize_text(row.get("PageName"))
    })
    distinct_languages = len([language for language in language_counts if language])
    distinct_sentiments = len([sentiment for sentiment in sentiment_counts if sentiment])
    distinct_posts = len(ordered_posts)

    has_language_filter = bool(_normalize_text((filters or {}).get("language")))
    has_sentiment_filter = bool(_normalize_text((filters or {}).get("sentiment")))

    visibility = {
        "comments_by_post": distinct_posts > 1,
        "comments_by_language": distinct_languages > 1 and not has_language_filter,
        "sentiment_by_language": distinct_languages > 1 and distinct_sentiments > 1 and not (has_language_filter or has_sentiment_filter),
        "sentiment_by_post": distinct_posts > 1 and distinct_sentiments > 1 and not has_sentiment_filter,
        "comment_length_histogram": len(rows) > 1,
        "avg_length_by_sentiment": distinct_sentiments > 1 and not has_sentiment_filter,
        "avg_length_by_language_sentiment": distinct_languages > 1 and distinct_sentiments > 1 and not (has_language_filter or has_sentiment_filter),
        "solidarity_distribution_by_language": distinct_posts > 1 and distinct_languages > 1 and not has_language_filter,
        "positivity_trend_overall": distinct_posts > 1 and distinct_sentiments > 1 and not has_sentiment_filter,
        "positivity_trend_by_language": distinct_posts > 1 and distinct_languages > 1 and distinct_sentiments > 1 and not (has_language_filter or has_sentiment_filter),
    }

    reasons = {}
    if distinct_pages <= 1:
        reasons["single_page_scope"] = "The current subset resolves to one page, so page-comparison charts are not needed."
    if has_language_filter:
        reasons["language_filter"] = "Language-comparison charts are hidden because the subset is already narrowed to one language."
    if has_sentiment_filter:
        reasons["sentiment_filter"] = "Sentiment-comparison charts are hidden because the subset is already narrowed to one sentiment."
    if distinct_posts <= 1:
        reasons["single_post_scope"] = "Post-level trend charts are hidden because fewer than two posts remain after filtering."

    return {
        "visible": visibility,
        "meta": {
            "distinct_pages": distinct_pages,
            "distinct_languages": distinct_languages,
            "distinct_sentiments": distinct_sentiments,
            "distinct_posts": distinct_posts,
        },
        "reasons": reasons,
    }


def build_analysis_from_rows(rows, selection_type=None, selection_value=None, filters=None):
    if not rows:
        return {
            "selection_type": selection_type,
            "selection_value": selection_value,
            "page_name": None,
            "page_id": None,
            "summary": None,
            "language_breakdown": [],
            "post_breakdown": [],
            "solidarity_breakdown": [],
            "sample_comments": [],
            "charts": {},
            "chart_visibility": {"visible": {}, "meta": {}, "reasons": {}},
        }

    first_row = rows[0]
    page_name = first_row.get("PageName")
    page_id = first_row.get("PageID")

    posts = defaultdict(list)
    sentiment_counts = Counter()
    language_counts = Counter()
    processed_times = []

    for row in rows:
        post_time = _normalize_datetime(row.get("PostTime"))
        comment_time = _normalize_datetime(row.get("CommentTime"))
        processed_time = _normalize_datetime(row.get("ProcessedTime"))
        filtered_comment = _normalize_text(row.get("FilteredComment"))
        sentiment = _normalize_text(row.get("Sentiment")).lower() or "unknown"
        language = _normalize_text(row.get("MainLanguage")).lower() or "unknown"

        row["_post_time_dt"] = post_time
        row["_comment_time_dt"] = comment_time
        row["_comment_length"] = len(filtered_comment.split()) if filtered_comment else 0
        row["_post_key"] = _build_post_key(row.get("PageID"), row.get("PageName"), post_time)

        posts[row["_post_key"]].append(row)
        sentiment_counts[sentiment] += 1
        language_counts[language] += 1
        if processed_time:
            processed_times.append(processed_time)

    post_anchor_sentiments = db_connection.fetch_post_anchor_sentiments([
        {
            "page_id": row_group[0].get("PageID") if row_group else None,
            "page_name": row_group[0].get("PageName") if row_group else None,
            "post_time": row_group[0].get("PostTime") if row_group else None,
        }
        for row_group in posts.values()
        if row_group
    ])

    ordered_posts = sorted(
        posts.items(),
        key=lambda item: (
            item[1][0]["_post_time_dt"] is None,
            item[1][0]["_post_time_dt"],
            _normalize_text(item[1][0].get("PageID")),
            _normalize_text(item[1][0].get("PageName")),
        ),
    )

    language_sentiments = defaultdict(Counter)
    comment_lengths_by_sentiment = defaultdict(list)
    comment_lengths_by_language_sentiment = defaultdict(list)
    positivity_by_language = defaultdict(lambda: {"total": 0, "positive": 0, "posts": defaultdict(lambda: {"total": 0, "positive": 0})})
    positivity_by_post = []
    solidarity_breakdown = []
    sample_comments = []

    for index, (_post_key, post_rows) in enumerate(ordered_posts, start=1):
        sorted_rows = sorted(
            post_rows,
            key=lambda row: (
                row["_comment_time_dt"] is None,
                row["_comment_time_dt"],
                row.get("CommentHash"),
            ),
        )
        post_time = sorted_rows[0]["_post_time_dt"] if sorted_rows else None

        post_sentiments = Counter()
        post_languages = Counter()
        positive_comments = 0

        for row in sorted_rows:
            sentiment = _normalize_text(row.get("Sentiment")).lower() or "unknown"
            language = _normalize_text(row.get("MainLanguage")).lower() or "unknown"
            post_sentiments[sentiment] += 1
            post_languages[language] += 1
            language_sentiments[language][sentiment] += 1
            comment_lengths_by_sentiment[sentiment].append(row["_comment_length"])
            comment_lengths_by_language_sentiment[(language, sentiment)].append(row["_comment_length"])
            positivity_by_language[language]["total"] += 1
            positivity_by_language[language]["posts"][index]["total"] += 1
            if sentiment == "positive":
                positive_comments += 1
                positivity_by_language[language]["positive"] += 1
                positivity_by_language[language]["posts"][index]["positive"] += 1

        positivity_by_post.append({
            "post_index": index,
            "post_time": post_time.isoformat(sep=" ") if post_time else "Unknown",
            "total_comments": len(sorted_rows),
            "positive_share": _safe_percentage(positive_comments, len(sorted_rows)),
            "top_language": post_languages.most_common(1)[0][0] if post_languages else "unknown",
            "sentiment_counts": {key: post_sentiments.get(key, 0) for key in SENTIMENT_ORDER},
            "sentiment_shares": {
                key: _safe_percentage(post_sentiments.get(key, 0), len(sorted_rows))
                for key in SENTIMENT_ORDER
            },
        })

        if sorted_rows:
            anchor_sentiment = post_anchor_sentiments.get(sorted_rows[0]["_post_key"], "unknown")
            comparable_rows = sorted_rows[1:] if len(sorted_rows) > 1 else []
            matches_by_language = defaultdict(lambda: {"matches": 0, "total": 0})
            for row in comparable_rows:
                language = _normalize_text(row.get("MainLanguage")).lower() or "unknown"
                sentiment = _normalize_text(row.get("Sentiment")).lower() or "unknown"
                matches_by_language[language]["total"] += 1
                if sentiment == anchor_sentiment:
                    matches_by_language[language]["matches"] += 1

            for language, stats in sorted(matches_by_language.items()):
                solidarity_breakdown.append({
                    "post_index": index,
                    "post_time": post_time.isoformat(sep=" ") if post_time else "Unknown",
                    "language": language,
                    "anchor_sentiment": anchor_sentiment,
                    "match_percent": _safe_percentage(stats["matches"], stats["total"]),
                    "compared_comments": stats["total"],
                })

        top_comment = max(
            sorted_rows,
            key=lambda row: (
                row.get("CommentLikes") is not None,
                row.get("CommentLikes") or 0,
                row["_comment_length"],
            ),
        )
        sample_comments.append({
            "post_index": index,
            "sentiment": _normalize_text(top_comment.get("Sentiment")).lower() or "unknown",
            "language": _normalize_text(top_comment.get("MainLanguage")).lower() or "unknown",
            "likes": top_comment.get("CommentLikes") or 0,
            "comment": _normalize_text(top_comment.get("Comment"))[:280],
        })

    language_breakdown = []
    for language in sorted(language_counts):
        sentiment_counter = language_sentiments[language]
        total = language_counts[language]
        language_breakdown.append({
            "language": language,
            "total_comments": total,
            "share_percent": _safe_percentage(total, len(rows)),
            "positive": sentiment_counter.get("positive", 0),
            "neutral": sentiment_counter.get("neutral", 0),
            "negative": sentiment_counter.get("negative", 0),
        })

    top_solidarity_posts = []
    post_comment_counts = {row["post_index"]: row["total_comments"] for row in positivity_by_post}
    for row in solidarity_breakdown:
        if row["language"] == "unknown":
            continue
        post_total_comments = post_comment_counts.get(row["post_index"], 0)
        comment_share = _safe_percentage(row["compared_comments"], post_total_comments)
        if comment_share < 15:
            continue
        top_solidarity_posts.append({
            "post_index": row["post_index"],
            "post_time": row["post_time"],
            "language": row["language"],
            "anchor_sentiment": row["anchor_sentiment"],
            "solidarity_score": row["match_percent"],
            "comment_share": comment_share,
            "compared_comments": row["compared_comments"],
            "post_total_comments": post_total_comments,
        })

    top_solidarity_posts.sort(
        key=lambda row: (-row["solidarity_score"], -row["comment_share"], row["post_index"], row["language"]),
    )

    latest_processed_time = max(processed_times).isoformat(sep=" ") if processed_times else None
    avg_comment_length = round(
        sum(row["_comment_length"] for row in rows) / len(rows),
        2,
    )

    comment_length_values = [row["_comment_length"] for row in rows]
    adaptive_histogram_bins = _build_adaptive_histogram_bins(comment_length_values)

    positivity_trend = []
    for row in positivity_by_post:
        positivity_trend.append({
            "label": f"P{row['post_index']}",
            "value": row["positive_share"],
        })

    positivity_by_language_series = []
    overall_language_totals = {
        language: stats["total"]
        for language, stats in positivity_by_language.items()
        if language != "unknown"
    }
    top_languages_for_trends = [
        language
        for language, _count in sorted(overall_language_totals.items(), key=lambda item: (-item[1], item[0]))[:3]
    ]
    for language in top_languages_for_trends:
        post_stats = positivity_by_language[language]["posts"]
        points = []
        for post_index in sorted(post_stats):
            total = post_stats[post_index]["total"]
            positive = post_stats[post_index]["positive"]
            points.append({
                "label": f"P{post_index}",
                "value": _safe_percentage(positive, total),
            })
        positivity_by_language_series.append({
            "name": language,
            "points": points,
        })

    solidarity_distribution = []
    solidarity_scores_by_language = defaultdict(list)
    for row in solidarity_breakdown:
        if row["language"] != "unknown":
            solidarity_scores_by_language[row["language"]].append(row["match_percent"])
    for language, values in sorted(solidarity_scores_by_language.items()):
        solidarity_distribution.append({
            "label": language,
            "value": _safe_average(values),
        })

    charts = {
        "comments_by_post": [
            {"label": f"P{row['post_index']}", "value": row["total_comments"]}
            for row in positivity_by_post
        ],
        "comments_by_language": [
            {"label": row["language"], "value": row["total_comments"]}
            for row in language_breakdown
        ],
        "sentiment_by_language": [
            {
                "label": row["language"],
                "positive": row["positive"],
                "neutral": row["neutral"],
                "negative": row["negative"],
            }
            for row in language_breakdown
        ],
        "sentiment_by_post": [
            {
                "label": f"P{row['post_index']}",
                "positive": row["sentiment_counts"]["positive"],
                "neutral": row["sentiment_counts"]["neutral"],
                "negative": row["sentiment_counts"]["negative"],
                "positive_share": row["sentiment_shares"]["positive"],
                "neutral_share": row["sentiment_shares"]["neutral"],
                "negative_share": row["sentiment_shares"]["negative"],
            }
            for row in positivity_by_post
        ],
        "comment_length_histogram": [
            {"label": bucket["label"], "value": bucket["value"]}
            for bucket in adaptive_histogram_bins
        ],
        "avg_length_by_sentiment": [
            {"label": sentiment, "value": _safe_average(values)}
            for sentiment, values in sorted(comment_lengths_by_sentiment.items())
        ],
        "avg_length_by_language_sentiment": [
            {
                "label": language,
                "sentiment": sentiment,
                "value": _safe_average(values),
            }
            for (language, sentiment), values in sorted(comment_lengths_by_language_sentiment.items())
            if language != "unknown"
        ],
        "solidarity_distribution_by_language": solidarity_distribution,
        "positivity_trend_overall": positivity_trend,
        "positivity_trend_by_language": positivity_by_language_series,
    }

    summary = {
        "total_comments": len(rows),
        "distinct_posts": len(ordered_posts),
        "page_name": page_name,
        "page_id": page_id,
        "languages": len(language_counts),
        "positive_share": _safe_percentage(sentiment_counts.get("positive", 0), len(rows)),
        "avg_comment_length": avg_comment_length,
        "latest_processed_time": latest_processed_time,
    }

    chart_visibility = _build_chart_visibility(filters, rows, language_counts, sentiment_counts, ordered_posts)

    return {
        "selection_type": selection_type,
        "selection_value": selection_value,
        "page_name": page_name,
        "page_id": page_id,
        "summary": summary,
        "language_breakdown": language_breakdown,
        "post_breakdown": positivity_by_post,
        "solidarity_breakdown": solidarity_breakdown,
        "solidarity_top_posts": top_solidarity_posts[:5],
        "sample_comments": sample_comments[:6],
        "charts": charts,
        "chart_visibility": chart_visibility,
    }


def build_page_analysis(selection_type, selection_value):
    rows = fetch_enriched_comments_for_page(selection_type, selection_value)
    return build_analysis_from_rows(
        rows,
        selection_type=selection_type,
        selection_value=selection_value,
        filters={selection_type: selection_value},
    )
