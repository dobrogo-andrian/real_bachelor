PAGE_SECTIONS = [
    {
        "title": "Home",
        "route": "/",
        "access": "Public",
        "summary": "Landing page for the whole workspace. It introduces the product, links to every main page, and reflects whether the visitor is already authenticated.",
        "details": [
            "Shows the current workspace scope: extractor, explorer, advanced analysis, FAQ, signup, and login.",
            "Detects an existing session from the browser and replaces login prompts with a logged-in indicator.",
            "Acts as the safest re-entry point when a user is deciding which workflow page to open next.",
        ],
    },
    {
        "title": "Login",
        "route": "/login",
        "access": "Public",
        "summary": "Authentication entry page for application users. Opening this page also resets any existing JWT cookie session before showing the form.",
        "details": [
            "Accepts the application username and password stored in the `Users` table.",
            "Uses the `next` query parameter to return the user to the protected page they originally requested.",
            "Always clears the current session on page load so the login form starts from a clean authentication state.",
        ],
    },
    {
        "title": "Sign Up",
        "route": "/signup",
        "access": "Public",
        "summary": "Account creation page for new operators. It creates the application account and stores encrypted Instagram credentials for later extraction jobs.",
        "details": [
            "Collects username, email, application password, Instagram login, and Instagram password.",
            "Hashes the application password before storage and protects Instagram credentials with reversible encryption.",
            "Prepares the user record so later workflows can use saved Instagram credentials without storing them as plaintext.",
        ],
    },
    {
        "title": "Extractor",
        "route": "/extractor",
        "access": "Authenticated",
        "summary": "Data ingestion page. It is responsible for starting the Instagram extraction flow and loading new comments into the database.",
        "details": [
            "Accepts a target page, number of posts, and Instagram credentials for the extraction session.",
            "Calls the backend extraction script and streams the resulting comment batches into SQL Server.",
            "Should be used first whenever fresh comments are needed before any analytical work can begin.",
        ],
    },
    {
        "title": "Explorer",
        "route": "/explorer",
        "access": "Authenticated",
        "summary": "Primary analysis page for page-level exploration. It lets the user select a page, run analysis, and inspect result summaries built from the warehouse.",
        "details": [
            "Loads distinct page names and page ids from the `Comments` table.",
            "Focuses on guided exploration rather than arbitrary row-level filtering.",
            "Works best when the user already knows which Instagram page or page id they want to review.",
        ],
    },
    {
        "title": "Advanced Analysis",
        "route": "/advanced-analysis",
        "access": "Authenticated",
        "summary": "Detailed filter workspace for enriched comments. It goes beyond Explorer by allowing direct row preview and more granular segment construction.",
        "details": [
            "Supports combined filtering by page name, page id, source, language, sentiment, likes, time windows, and text search.",
            "Returns both row previews and aggregated analysis derived from the filtered subset.",
            "Is the right page when the user needs precise slices of the dataset instead of a broader page-level overview.",
        ],
    },
    {
        "title": "FAQ",
        "route": "/faq",
        "access": "Authenticated",
        "summary": "Reference page for the entire application. It documents what every page does, how the data model is structured, and how the processing pipeline is organized.",
        "details": [
            "Keeps product and technical reference material separate from the live analysis workflows.",
            "Documents the shared source tables, enrichment stages, and intended responsibilities of each page.",
            "Also contains the contact section for questions, handoff notes, or future maintenance work.",
        ],
    },
    {
        "title": "Elements",
        "route": "/elements",
        "access": "Authenticated",
        "summary": "Template support page inherited from the base theme. It is not part of the main analysis workflow but remains available as a design and component reference.",
        "details": [
            "Useful when comparing existing UI components from the HTML template.",
            "Can be removed later if the project no longer needs the theme reference page.",
            "Should not be presented as a core analytical step for end users.",
        ],
    },
    {
        "title": "Test",
        "route": "/test",
        "access": "Public",
        "summary": "Utility page for local experiments and temporary checks. It is not a documented end-user workflow page.",
        "details": [
            "Can be used for isolated frontend or backend verification during development.",
            "Should stay clearly separated from the production-facing navigation.",
            "May be removed or repurposed once its temporary development value is gone.",
        ],
    },
]


FAQ_REFERENCE = {
    "schema_columns": [
        {"name": "CommentHash", "role": "Primary key", "description": "Stable SHA-256 identifier used for deduplication and upserts."},
        {"name": "PageName", "role": "Dimension", "description": "Display name of the Instagram page for grouping and filtering."},
        {"name": "PageID", "role": "Dimension", "description": "Stable page handle used as the main entity key in the UI."},
        {"name": "PostTime", "role": "Timeline anchor", "description": "Lets the interface build post-order and trend analysis over time."},
        {"name": "Comment", "role": "Core text", "description": "Raw input for language detection, sentiment, and qualitative review."},
        {"name": "CommentTime", "role": "Event time", "description": "Supports response windows, posting rhythm, and freshness filters."},
        {"name": "CommentLikes", "role": "Engagement signal", "description": "Weights notable comments and highlights audience resonance."},
        {"name": "LoadTime", "role": "Ingestion audit", "description": "Tracks when comments were loaded into the warehouse."},
        {"name": "Source", "role": "Lineage", "description": "Separates web-ingested data from future loaders or imports."},
    ],
    "pipeline_steps": [
        {
            "title": "1. Source Selection",
            "module": "Comments table",
            "description": "choose a page, period, source, and post window from the central table before any derived analysis runs.",
        },
        {
            "title": "2. Language Processing",
            "module": "enrich_comments.py",
            "description": "Normalize comment text, detect the dominant language, and prepare consistent text for downstream analysis.",
        },
        {
            "title": "3. Sentiment Scoring",
            "module": "enrich_comments.py",
            "description": "Run the language-specific sentiment models and classify comments as positive, neutral, or negative.",
        },
        {
            "title": "4. Dataset Assembly",
            "module": "explorer_analysis.py",
            "description": "Group enriched rows into post-level and language-level structures for chart-ready output.",
        },
        {
            "title": "5. Insight Views",
            "module": "explorer.html / advanced_analysis.html",
            "description": "Render exploratory charts, direct row previews, and drill-downs from the enriched dataset.",
        },
    ],
    "implementation_notes": [
        "Use the `Comments` table as the source of truth for filtering and retrieval.",
        "Move heavy processing into explicit backend stages or precomputed tables.",
        "Keep chart clicks connected to raw comments for validation.",
        "Use the FAQ page as product and technical reference for future contributors.",
    ],
    "advanced_filters": [
        {
            "name": "Page name",
            "meaning": "Restricts the dataset to one or more display names from `EnrichedComments.PageName`.",
        },
        {
            "name": "Page id",
            "meaning": "Restricts the dataset to one or more stable page identifiers from `EnrichedComments.PageID`.",
        },
        {
            "name": "Source",
            "meaning": "Keeps only rows loaded from the selected ingestion source or loader lineage value.",
        },
        {
            "name": "Main language",
            "meaning": "Limits rows to comments whose detected dominant language matches the selected values.",
        },
        {
            "name": "Sentiment",
            "meaning": "Filters individual comments by their own sentiment label: positive, neutral, or negative.",
        },
        {
            "name": "Post description sentiment",
            "meaning": "Filters posts by the sentiment of the first comment in the full unfiltered post, used as the post anchor.",
        },
        {
            "name": "Minimum comment likes",
            "meaning": "Keeps only comments whose `CommentLikes` value is greater than or equal to the chosen threshold.",
        },
        {
            "name": "Post time from / to",
            "meaning": "Restricts the subset by the publication time of the post itself, not the comment time.",
        },
        {
            "name": "Comment time from / to",
            "meaning": "Restricts the subset by when the comment was created, useful for response-window analysis.",
        },
        {
            "name": "Comment text search",
            "meaning": "Matches rows where the raw comment text or filtered comment text contains the given phrase or keyword.",
        },
    ],
}
