CREATE TABLE [dbo].[Comments](
    [CommentHash] [char](64) NOT NULL,
    [PageName] [nvarchar](100) NOT NULL,
    [PageID] [nvarchar](100) NOT NULL,
    [PostTime] [datetime2](0) NULL,
    [Comment] [nvarchar](max) NOT NULL,
    [CommentTime] [datetime2](0) NULL,
    [CommentLikes] [int] NULL,
    [LoadTime] [datetime2](0) NOT NULL CONSTRAINT [DF_Comments_LoadTime] DEFAULT (SYSUTCDATETIME()),
    [UpdateTime] [datetime2](0) NULL,
    [Source] [nvarchar](50) NULL,
PRIMARY KEY CLUSTERED
(
    [CommentHash] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
