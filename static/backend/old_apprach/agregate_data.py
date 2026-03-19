import os
import pandas as pd
from static.backend.common_utils import get_next_filename, extract_sort_key


def collect_and_prepare_data(input_folder, output_file):
    """
    Збирає всі файли з коментарями, додає id (з назви файлу) та sub_id (нумерація коментарів),
    і об'єднує всі дані в один датасет.
    :param input_folder: шлях до папки з вхідними файлами
    :param output_file: шлях до вихідного CSV-файлу
    """
    combined_data = []

    input_files = [f for f in os.listdir(input_folder) if f.endswith('.csv')]
    input_files = sorted(input_files, key=extract_sort_key)

    for input_file in input_files:
        file_id = int(input_file.split('_')[-1].split('.')[0])

        file_path = os.path.join(input_folder, input_file)
        df = pd.read_csv(file_path)

        df['id'] = file_id
        df['sub_id'] = range(1, len(df) + 1)

        combined_data.append(df)

    combined_df = pd.concat(combined_data, ignore_index=True)

    column_order = ['id', 'sub_id', 'Main_Language', 'Sentiment', 'Filtered_Comment']
    combined_df = combined_df[column_order]

    combined_df.to_csv(output_file, index=False)
    print(f"Об'єднаний датасет збережено в: {output_file}")


def aggregate_data(input_folder="sentiment_analysis\\additional_task\\politics",
                   output_folder="final_dataset\\additional_task\\politics"):
    output_path = get_next_filename("combined_comments", output_folder)

    print(f"Обробляємо файли: {input_folder}\\")
    collect_and_prepare_data(input_folder, output_path)
    print(f"Результат збережено в: {output_path}")
