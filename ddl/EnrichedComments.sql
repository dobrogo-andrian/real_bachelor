CREATE TABLE [dbo].[EnrichedComments](
    [CommentHash] [char](64) NOT NULL,
    [PageName] [nvarchar](100) NOT NULL,
    [PageID] [nvarchar](100) NOT NULL,
    [PostTime] [datetime2](0) NULL,
    [Comment] [nvarchar](max) NOT NULL,
    [CommentTime] [datetime2](0) NULL,
    [CommentLikes] [int] NULL,
    [MainLanguage] [nvarchar](20) NOT NULL,
    [FilteredComment] [nvarchar](max) NULL,
    [Sentiment] [nvarchar](20) NOT NULL,
    [ProcessedTime] [datetime2](0) NOT NULL CONSTRAINT [DF_EnrichedComments_ProcessedTime] DEFAULT (SYSUTCDATETIME()),
    [UpdateTime] [datetime2](0) NULL,
    [Source] [nvarchar](50) NULL,
PRIMARY KEY CLUSTERED
(
    [CommentHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
CONSTRAINT [FK_EnrichedComments_Comments] FOREIGN KEY([CommentHash])
REFERENCES [dbo].[Comments] ([CommentHash]),
CONSTRAINT [CK_EnrichedComments_MainLanguage] CHECK ([MainLanguage] IN (N'uk', N'ru', N'en', N'symbols_only', N'unknown')),
CONSTRAINT [CK_EnrichedComments_Sentiment] CHECK ([Sentiment] IN (N'positive', N'neutral', N'negative'))
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_PageName]
ON [dbo].[EnrichedComments] ([PageName] ASC)
ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_PageID]
ON [dbo].[EnrichedComments] ([PageID] ASC)
ON [PRIMARY]
GO

CREATE NONCLUSTERED INDEX [IX_EnrichedComments_Sentiment]
ON [dbo].[EnrichedComments] ([Sentiment] ASC)
ON [PRIMARY]
GO
