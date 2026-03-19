import pandas as pd
from langdetect import detect_langs
import re
import unicodedata
import os
from static.backend.common_utils import get_next_filename, extract_sort_key


def normalize_unicode(text):
    """
    Нормалізує текст до форми NFC, щоб об'єднати комбіновані символи.
    :param text: текст для нормалізації
    :return: нормалізований текст
    """
    return unicodedata.normalize('NFC', text)


def clean_text(comment):
    """
    Очищує текст, залишаючи лише символи англійського, російського та українського алфавітів.
    :param comment: текст коментаря
    :return: очищений текст
    """
    comment = normalize_unicode(comment)
    return re.sub(r'[^a-zA-Zа-яА-ЯёЁіІїЇєЄґҐйЙ\s]', '', comment)


def detect_main_language(comment):
    """
    Визначає основну мову для всього коментаря.
    :param comment: текст коментаря
    :return: код основної мови ('uk', 'ru', 'en', 'symbols_only')
    """
    if all(not char.isalnum() for char in comment):
        return "symbols_only"

    try:
        langs = detect_langs(comment)
        main_language = max(langs, key=lambda lang: lang.prob).lang
        if main_language in ['uk', 'ru', 'en']:
            return main_language
        else:
            return "unknown"
    except:
        return "unknown"


def filter_comment_by_main_language(comment, main_language):
    """
    Залишає в коментарі лише слова, які відповідають алфавіту основної мови.
    :param comment: текст коментаря
    :param main_language: код основної мови ('uk', 'ru', 'en', 'symbols_only')
    :return: коментар із залишеними лише словами основної мови
    """
    if main_language == "uk":
        allowed_pattern = r'^[а-яА-ЯёЁіІїЇєЄґҐйЙ!?]+$'
    elif main_language == "ru":
        allowed_pattern = r'^[а-яА-ЯёЁ!?]+$'
    elif main_language == "en":
        allowed_pattern = r'^[a-zA-Z!?]+$'
    else:
        return comment

    words = comment.split()

    filtered_words = [word for word in words if re.match(allowed_pattern, word)]

    return " ".join(filtered_words)


def process_csv(input_csv, output_csv):
    """
    Обробляє CSV-файл, визначає основну мову для кожного коментаря,
    залишає лише слова основної мови і створює новий CSV-файл.
    :param input_csv: шлях до вхідного CSV-файлу
    :param output_csv: шлях до вихідного CSV-файлу
    """
    df = pd.read_csv(input_csv)

    if 'Comment' not in df.columns:
        raise ValueError("Вхідний файл повинен містити стовпець 'Comment'.")

    filtered_data = []
    for comment in df['Comment']:
        comment = str(comment)
        main_language = detect_main_language(comment)

        if main_language not in ['uk', 'ru', 'en', 'symbols_only']:
            main_language = "unknown"

        if main_language == "unknown":
            continue

        if main_language == "symbols_only":
            filtered_comment = comment
        else:
            filtered_comment = filter_comment_by_main_language(comment, main_language)

        if filtered_comment:
            filtered_data.append({'Main_Language': main_language, 'Filtered_Comment': filtered_comment})

    filtered_df = pd.DataFrame(filtered_data)

    filtered_df.to_csv(output_csv, index=False)
    print(f"Файл успішно оброблено! Результат збережено в {output_csv}")


def process_data( input_folder= "unprocessed_data/comments1",
                 output_folder = "language_marked_comments/additional_task",
                 main_languages = ("uk", "en", "ru", "symbols_only")
                  ):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    input_files = [f for f in os.listdir(input_folder) if f.endswith('.csv')]
    input_files = sorted(input_files, key=extract_sort_key)

    for input_file in input_files:
        input_csv_path = os.path.join(input_folder, input_file)
        output_path = get_next_filename("comments_with_languages_filtered", output_folder)
        print(f"Обробляємо файл: {input_csv_path}")
        process_csv(input_csv_path, output_path)
        print(f"Результат збережено в: {output_path}")

    print("all avaliblle data is processed")

























