CREATE TABLE [dbo].[Users](
    [UserID] [int] IDENTITY(1,1) NOT NULL,
    [Username] [nvarchar](50) NOT NULL,
    [PasswordHash] [nvarchar](512) NOT NULL,
    [Email] [nvarchar](100) NOT NULL,
    [EmailVerified] [bit] NOT NULL CONSTRAINT [DF_Users_EmailVerified] DEFAULT ((0)),
    [EmailVerifiedAt] [datetime2](0) NULL,
    [InstagramLoginEncrypted] [varbinary](max) NULL,
    [InstagramPasswordEncrypted] [varbinary](max) NULL,
    [InstagramCookiesEncrypted] [varbinary](max) NULL,
    [InstagramCookiesSignature] [varbinary](64) NULL,
    [InstagramCookiesUpdatedAt] [datetime2](0) NULL,
    [CreatedAt] [datetime2](0) NOT NULL CONSTRAINT [DF_Users_CreatedAt] DEFAULT SYSUTCDATETIME(),
    [PasswordChangedAt] [datetime2](0) NOT NULL CONSTRAINT [DF_Users_PasswordChangedAt] DEFAULT SYSUTCDATETIME(),
PRIMARY KEY CLUSTERED
(
    [UserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
UNIQUE NONCLUSTERED
(
    [Username] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY],
UNIQUE NONCLUSTERED
(
    [Email] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
