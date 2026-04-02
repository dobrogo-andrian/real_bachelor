CREATE TABLE [dbo].[Comments](
    [CommentHash] [char](64) NOT NULL,
    [PageName] [nvarchar](100) NOT NULL,
    [PageID] [nvarchar](100) NOT NULL,
    [PostHref] [nvarchar](2048) NULL,
    [PostTime] [datetime2](0) NULL,
    [Comment] [nvarchar](max) NOT NULL,
    [CommentTime] [datetime2](0) NULL,
    [CommentLikes] [int] NULL,
    [LoadTime] [datetime2](0) NOT NULL CONSTRAINT [DF_Comments_LoadTime] DEFAULT (SYSUTCDATETIME()),
PRIMARY KEY CLUSTERED
(
    [CommentHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_Comments_PageName]
ON [dbo].[Comments] ([PageName] ASC)
ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_Comments_PageID_PostHref]
ON [dbo].[Comments] ([PageID] ASC)
INCLUDE ([PostHref])
WHERE [PostHref] IS NOT NULL
GO

CREATE NONCLUSTERED INDEX [IX_Comments_PageID_PostTime_CommentTime]
ON [dbo].[Comments] (
    [PageID] ASC,
    [PostTime] ASC,
    [CommentTime] ASC,
    [CommentHash] ASC
)
INCLUDE ([PageName], [CommentLikes])
ON [PRIMARY]
GO
