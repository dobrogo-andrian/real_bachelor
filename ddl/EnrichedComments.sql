CREATE TABLE [dbo].[EnrichedComments](
    [CommentHash] [char](64) NOT NULL,
    [PageName] [nvarchar](100) NOT NULL,
    [PageID] [nvarchar](100) NOT NULL,
    [PostHref] [nvarchar](2048) NULL,
    [PostTime] [datetime2](0) NULL,
    [CommentTime] [datetime2](0) NULL,
    [CommentOrder] [int] NULL,
    [CommentLikes] [int] NULL,
    [MainLanguage] [nvarchar](20) NOT NULL,
    [NormalizedComment] [nvarchar](max) NULL,
    [Sentiment] [nvarchar](20) NOT NULL,
    [ProcessedTime] [datetime2](0) NOT NULL CONSTRAINT [DF_EnrichedComments_ProcessedTime] DEFAULT (SYSUTCDATETIME()),
    [Source] [nvarchar](50) NULL,
PRIMARY KEY CLUSTERED
(
    [CommentHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
CONSTRAINT [FK_EnrichedComments_Comments] FOREIGN KEY([CommentHash])
REFERENCES [dbo].[Comments] ([CommentHash]),
CONSTRAINT [CK_EnrichedComments_MainLanguage] CHECK ([MainLanguage] IN (N'uk', N'ru', N'en', N'symbols_only', N'other')),
CONSTRAINT [CK_EnrichedComments_Sentiment] CHECK ([Sentiment] IN (N'positive', N'neutral', N'negative'))
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_PageName_PostWindow]
ON [dbo].[EnrichedComments] (
    [PageName] ASC,
    [PostTime] DESC,
    [CommentTime] DESC,
    [CommentHash] ASC
)
INCLUDE ([PageID], [CommentOrder], [CommentLikes], [MainLanguage], [Sentiment], [ProcessedTime], [Source])
ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_PageID_PostWindow]
ON [dbo].[EnrichedComments] (
    [PageID] ASC,
    [PostTime] DESC,
    [CommentTime] DESC,
    [CommentHash] ASC
)
INCLUDE ([PageName], [CommentOrder], [CommentLikes], [MainLanguage], [Sentiment], [ProcessedTime], [Source])
ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_PostAnchor]
ON [dbo].[EnrichedComments] (
    [PageID] ASC,
    [PageName] ASC,
    [PostTime] ASC,
    [CommentTime] ASC,
    [CommentHash] ASC
)
INCLUDE ([Sentiment])
ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_Source_Language_Sentiment]
ON [dbo].[EnrichedComments] (
    [Source] ASC,
    [MainLanguage] ASC,
    [Sentiment] ASC,
    [PostTime] DESC,
    [CommentTime] DESC,
    [CommentHash] ASC
)
INCLUDE ([PageID], [PageName], [CommentLikes], [ProcessedTime])
ON [PRIMARY]
GO
