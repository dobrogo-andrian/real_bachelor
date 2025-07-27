from transformers import pipeline
import pandas as pd
import os
import re


def load_models():
    """
    Завантажує моделі для аналізу тональності залежно від мови.
    :return: словник із моделями для кожної мови
    """
    models = {
        "uk": pipeline("sentiment-analysis", model="cardiffnlp/twitter-xlm-roberta-base-sentiment"),
        "ru": pipeline("sentiment-analysis", model="blanchefort/rubert-base-cased-sentiment"),
        "en": pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-sentiment"),
        "symbols_only": pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-sentiment"),
    }
    return models


def analyze_sentiment(comment, language, models):
    """
    Аналізує тональність коментаря залежно від його мови.
    :param comment: текст коментаря
    :param language: мова коментаря ('uk', 'ru', 'en', 'symbols_only')
    :param models: словник із завантаженими моделями
    :return: оцінка тональності ('positive', 'neutral', 'negative')
    """
    if language == "symbols_only":
        # Використовуємо модель для аналізу емодзі та символів
        try:
            result = models[language](comment)
            label = result[0]['label']  # Наприклад, 'label_0', 'label_1', 'label_2'
            # Перетворюємо мітки на текстові оцінки
            if label == "LABEL_0" or label == "label_0":
                return "negative"
            elif label == "LABEL_1" or label == "label_1":
                return "neutral"
            elif label == "LABEL_2" or label == "label_2":
                return "positive"
        except Exception as e:
            print(f"Помилка аналізу тональності для символів: {comment}. Помилка: {e}")
            return "neutral"

    if language not in models:
        return "neutral"  # Якщо модель для мови не завантажена, повертаємо нейтральну оцінку

    try:
        result = models[language](comment)
        label = result[0]['label']  # Наприклад, 'label_0', 'label_1', 'label_2'
        # Перетворюємо мітки на текстові оцінки
        if label == "LABEL_0" or label == "label_0" or str.lower(label) == "negative":
            return "negative"
        elif label == "LABEL_1" or label == "label_1" or str.lower(label) == "neutral":
            return "neutral"
        elif label == "LABEL_2" or label == "label_2" or str.lower(label) == "positive":
            return "positive"
    except Exception as e:
        print(f"Помилка аналізу тональності для коментаря: {comment}. Помилка: {e}")
        return "neutral"


def process_sentiment_analysis(input_csv, output_csv):
    """
    Обробляє CSV-файл, аналізує тональність коментарів і створює новий CSV-файл.
    :param input_csv: шлях до вхідного CSV-файлу
    :param output_csv: шлях до вихідного CSV-файлу
    """
    # Завантажуємо CSV-файл
    df = pd.read_csv(input_csv)

    # Перевіряємо, чи є необхідні стовпці
    if 'Filtered_Comment' not in df.columns or 'Main_Language' not in df.columns:
        raise ValueError("Вхідний файл повинен містити стовпці 'Filtered_Comment' і 'Main_Language'.")

    models = load_models()

    sentiments = []
    for comment, language in zip(df['Filtered_Comment'], df['Main_Language']):
        sentiment = analyze_sentiment(comment, language, models)
        sentiments.append(sentiment)

    df['Sentiment'] = sentiments

    df.to_csv(output_csv, index=False)
    print(f"Файл успішно оброблено! Результат збережено в {output_csv}")


def get_next_filename(base_filename, folder):
    """
    Генерує унікальну назву файлу, додаючи +1 до номера.
    """
    if not os.path.exists(folder):
        os.makedirs(folder)

    files = os.listdir(folder)

    matching_files = [f for f in files if f.startswith(base_filename) and f.endswith(".csv")]

    max_number = 0
    for file in matching_files:
        try:
            number = int(file.replace(base_filename, "").replace(".csv", "").strip("_"))
            if number > max_number:
                max_number = number
        except ValueError:
            continue

    next_number = max_number + 1
    return os.path.join(folder, f"{base_filename}_{next_number}.csv")


def analyze_data(input_folder="language_marked_comments/additional_task",
                 output_folder="sentiment_analysis/additional_task"):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    input_files = [f for f in os.listdir(input_folder) if f.endswith('.csv')]
    input_files = sorted(input_files, key=lambda x: int(re.search(r'\d+', x).group()))
    for input_file in input_files:
        try:
            input_csv_path = os.path.join(input_folder, input_file)
            output_path = get_next_filename("comments_with_languages_filtered", output_folder)

            print(f"Обробляємо файл: {input_csv_path}")
            process_sentiment_analysis(input_csv_path, output_path)
            print(f"Результат збережено в: {output_path}")
        except Exception as e:
            continue
    print("all available data is analyzed")
