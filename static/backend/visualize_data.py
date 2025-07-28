import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from statsmodels.nonparametric.smoothers_lowess import lowess


file_path = "final_dataset/combined_comments_1.csv"
df = pd.read_csv(file_path)








### секція з eda









#### кількість коментарів для всіх дописів
sns.countplot(x='id', data=df, hue='id', palette="viridis", dodge=False, legend=False)
plt.title('Розподіл коментарів за id')
plt.xlabel('ID допису')
plt.ylabel('Кількість коментарів')
plt.show()


#### розподіл коментарів за мовами та тональністю
language_counts = df['Main_Language'].value_counts()
sns.barplot(x=language_counts.index, y=language_counts.values, hue=language_counts.index, palette="coolwarm", dodge=False, legend=False)
plt.title('Розподіл коментарів за мовами')
plt.xlabel('Мова')
plt.ylabel('Кількість коментарів')
plt.show()

sns.countplot(x='Main_Language', hue='Sentiment', data=df, palette="Set2")
plt.title('Тональність коментарів для кожної мови')
plt.xlabel('Мова')
plt.ylabel('Кількість коментарів')
plt.legend(title="Sentiment")
plt.show()



#### тоналність коментарів для кожного допису
sns.countplot(x='id', hue='Sentiment', data=df, palette="husl", dodge=False, legend=True)
plt.title('Тональність коментарів для кожного id')
plt.xlabel('ID допису')
plt.ylabel('Кількість коментарів')
plt.legend(title="Sentiment")
plt.show()



#### розподіл довжини коментарів
df['comment_length'] = df['Filtered_Comment'].apply(lambda x: len(str(x).split()))

sns.histplot(df['comment_length'], bins=30, kde=True, color="blue")
plt.title('Розподіл довжини коментарів після фільтрації')
plt.xlabel('Довжина коментаря (кількість слів)')
plt.ylabel('Кількість коментарів')
plt.show()


#### Зв’язок між довжиною коментаря та тональністю
sns.boxplot(x='Sentiment', y='comment_length', data=df, hue='Sentiment', palette="cool", dodge=False, legend=False)
plt.title('Зв’язок між довжиною коментаря та тональністю')
plt.xlabel('Тональність')
plt.ylabel('Довжина коментаря')
plt.show()



#### Зв’язок між мовою, довжиною коментаря та тональністю
sns.boxplot(x='Main_Language', y='comment_length', hue='Sentiment', data=df, palette="muted")
plt.title('Зв’язок між мовою, довжиною коментаря та тональністю')
plt.xlabel('Мова')
plt.ylabel('Довжина коментаря')
plt.legend(title="Sentiment")
plt.show()











### секція з аналізом








#### аналіз satiment для кожного допису
first_comments = df[df['sub_id'] == 1][['id', 'Sentiment']].rename(columns={'Sentiment': 'description_sentiment'})

other_comments = df[df['sub_id'] != 1]
merged_df = other_comments.merge(first_comments, on='id')

merged_df['matches_description'] = merged_df['Sentiment'] == merged_df['description_sentiment']

result = (
    merged_df
    .groupby(['id', 'Main_Language'], group_keys=False)
    .apply(lambda group: group['matches_description'].mean() * 100, include_groups=False)
    .reset_index(name='percent_matches')
)

print(result)

unique_ids = result['id'].unique()

for post_id in unique_ids:
    post_data = result[result['id'] == post_id]
    sentiment_data = merged_df[merged_df['id'] == post_id]

    sentiment_counts = (
        sentiment_data
        .groupby(['Main_Language', 'Sentiment'])
        .size()
        .reset_index(name='count')
    )

    plt.figure(figsize=(10, 6))
    ax = sns.barplot(
        x='Main_Language',
        y='count',
        hue='Sentiment',
        data=sentiment_counts,
        palette="Set2"
    )

    for bar in ax.patches:
        value = bar.get_height()
        x = bar.get_x() + bar.get_width() / 2
        ax.text(x, value + 1, f'{int(value)}', ha='center', va='bottom', fontsize=10)

    plt.title(f"Кількість коментарів за Sentiment для допису {post_id}", fontsize=16)
    plt.xlabel("Мова", fontsize=12)
    plt.ylabel("Кількість коментарів", fontsize=12)
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.show()

    plt.figure(figsize=(10, 6))
    ax = sns.barplot(
        x='Main_Language',
        y='percent_matches',
        data=post_data,
        palette="viridis",
        errorbar=None,
        hue=x
    )

    for bar in ax.patches:
        value = bar.get_height()
        x = bar.get_x() + bar.get_width() / 2
        ax.text(x, value + 1, f'{value:.1f}%', ha='center', va='bottom', fontsize=10)

    plt.title(f"Solidarity index для допису {post_id}", fontsize=16)
    plt.xlabel("Мова", fontsize=12)
    plt.ylabel("Відсоток співпадінь (%)", fontsize=12)
    plt.ylim(0, 100)
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.show()




### аналіз цілого датасету
stats = result.groupby('Main_Language')['percent_matches'].describe()
print("Описова статистика для кожної мови:")
print(stats)


plt.figure(figsize=(10, 6))
sns.boxplot(x='Main_Language', y='percent_matches', data=result, palette="Set2", hue=x)
plt.title("Solidarity index для кожної мови", fontsize=16)
plt.xlabel("Мова", fontsize=12)
plt.ylabel("Відсоток співпадінь (%)", fontsize=12)
plt.ylim(0, 100)
plt.show()

plt.figure(figsize=(10, 6))
sns.barplot(x='Main_Language', y='percent_matches', data=result, palette="coolwarm", errorbar=None, hue=x)
plt.title("Середній Solidarity index для кожної мови", fontsize=16)
plt.xlabel("Мова", fontsize=12)
plt.ylabel("Середній відсоток співпадінь (%)", fontsize=12)
plt.ylim(0, 100)
plt.show()

plt.figure(figsize=(10, 6))
sns.histplot(data=result, x='percent_matches', hue='Main_Language', kde=True, palette="husl", bins=20)
plt.title("Розподіл Solidarity index для всіх мов", fontsize=16)
plt.xlabel("Відсоток співпадінь (%)", fontsize=12)
plt.ylabel("Частота", fontsize=12)
plt.xlim(0, 100)
plt.show()





#### розрахування настрою
df['is_positive'] = df['Sentiment'] == 'positive'

positivity_by_language = (
    df.groupby(['id', 'Main_Language'])
    .agg(total_comments=('Sentiment', 'size'), positive_comments=('is_positive', 'sum'))
    .assign(positivity=lambda x: x['positive_comments'] / x['total_comments'])
    .reset_index()
)

positivity_overall = (
    df.groupby('id')
    .agg(total_comments=('Sentiment', 'size'), positive_comments=('is_positive', 'sum'))
    .assign(positivity=lambda x: x['positive_comments'] / x['total_comments'])
    .reset_index()
)
positivity_overall['Main_Language'] = 'all'

positivity_combined = pd.concat([positivity_by_language, positivity_overall], ignore_index=True)

languages = positivity_combined['Main_Language'].unique()

for language in languages:
    language_data = positivity_combined[positivity_combined['Main_Language'] == language]

    smoothed = lowess(
        language_data['positivity'],
        language_data['id'],
        frac=0.3
    )

    plt.figure(figsize=(10, 6))
    plt.plot(language_data['id'], language_data['positivity'], 'o', label="Дані", alpha=0.7)
    plt.plot(smoothed[:, 0], smoothed[:, 1], '-', label="Згладжений тренд", color="red")

    plt.title(f"Зміна позитивності настрою з часом ({language})", fontsize=16)
    plt.xlabel("ID допису (часова шкала)", fontsize=12)
    plt.ylabel("Позитивність настрою", fontsize=12)
    plt.ylim(0, 1)
    plt.xticks(range(1, 21))
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend()

    plt.tight_layout()
    plt.show()
















