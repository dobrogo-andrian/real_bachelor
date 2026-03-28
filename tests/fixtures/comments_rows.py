from datetime import datetime


def load_to_db_input_rows():
    return [
        {
            "Comment": "First",
            "Time": "2024-01-01 09:10:11",
            "Likes": "5",
            "PageName": "",
            "PageID": "",
        },
        {
            "Comment": "Second",
            "Time": "invalid-time",
            "Likes": "",
            "PageName": "Custom Page",
            "PageID": "custom-page-id",
        },
    ]


def enrich_comment_rows():
    return [
        {
            "CommentHash": "hash-1",
            "PageName": "Page",
            "PageID": "page-id",
            "PostHref": "href",
            "PostTime": datetime(2024, 1, 1, 10, 0, 0, 111),
            "Comment": "Hello",
            "CommentTime": datetime(2024, 1, 1, 10, 1, 0, 222),
            "CommentLikes": 7,
        },
        {
            "CommentHash": "hash-2",
            "PageName": "Page",
            "PageID": "page-id",
            "PostHref": "href",
            "PostTime": datetime(2024, 1, 1, 10, 0, 0),
            "Comment": "World",
            "CommentTime": datetime(2024, 1, 1, 10, 2, 0),
            "CommentLikes": 3,
        },
    ]
