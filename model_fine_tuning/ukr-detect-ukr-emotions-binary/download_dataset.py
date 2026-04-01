"""
Download and save the Hugging Face dataset:
    ukr-detect/ukr-emotions-binary

By default, this script saves:
    1. the full DatasetDict via save_to_disk() under ./hf_saved_dataset
    2. each split as a readable CSV in the same output directory

Usage examples:
    python download_dataset.py
    python download_dataset.py --output-dir ".\\hf_saved_dataset"
"""

from __future__ import annotations

import argparse
import os

import pandas as pd
from datasets import DatasetDict, get_dataset_split_names, load_dataset


DATASET_NAME = "ukr-detect/ukr-emotions-binary"
NEGATIVE = 0
NEUTRAL = 1
POSITIVE = 2
LABEL_NAMES = {
    NEGATIVE: "negative",
    NEUTRAL: "neutral",
    POSITIVE: "positive",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and save ukr-detect/ukr-emotions-binary locally.")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(".", "hf_saved_dataset"),
        help="Directory where the dataset will be saved via save_to_disk().",
    )
    return parser.parse_args()


def map_emotions_to_sentiment(row: pd.Series) -> int:
    joy = int(row.get("Joy", 0) or 0)
    fear = int(row.get("Fear", 0) or 0)
    anger = int(row.get("Anger", 0) or 0)
    sadness = int(row.get("Sadness", 0) or 0)
    disgust = int(row.get("Disgust", 0) or 0)
    surprise = int(row.get("Surprise", 0) or 0)

    has_negative = any([fear, anger, sadness, disgust])
    if has_negative:
        return NEGATIVE
    if joy or surprise:
        return POSITIVE
    return NEUTRAL


def evenly_spaced_indices(total_count: int, target_count: int) -> list[int]:
    if target_count <= 0 or total_count <= 0:
        return []
    if target_count >= total_count:
        return list(range(total_count))
    if target_count == 1:
        return [total_count // 2]

    indices = []
    for step in range(target_count):
        position = round(step * (total_count - 1) / (target_count - 1))
        indices.append(int(position))
    return sorted(set(indices))


def build_balanced_sentiment_dataframe(dataset_dict: DatasetDict) -> tuple[pd.DataFrame, pd.DataFrame]:
    split_frames = []
    for split_name, split_dataset in dataset_dict.items():
        frame = split_dataset.to_pandas()
        frame["source_split"] = split_name
        split_frames.append(frame)

    merged_frame = pd.concat(split_frames, ignore_index=True)
    merged_frame["sentiment_label"] = merged_frame.apply(map_emotions_to_sentiment, axis=1)
    merged_frame["sentiment_name"] = merged_frame["sentiment_label"].map(LABEL_NAMES)

    class_counts = merged_frame["sentiment_name"].value_counts().to_dict()
    print(f"[stats] mapped sentiment counts: {class_counts}")

    target_per_class = int(min(class_counts.values()))
    print(f"[stats] balanced rows per sentiment class: {target_per_class}")

    balanced_parts = []
    for sentiment_label, sentiment_name in LABEL_NAMES.items():
        class_frame = merged_frame[merged_frame["sentiment_label"] == sentiment_label].reset_index(drop=True)
        selected_idx = evenly_spaced_indices(len(class_frame), target_per_class)
        balanced_parts.append(class_frame.iloc[selected_idx].copy())

    balanced_frame = pd.concat(balanced_parts, ignore_index=True)
    balanced_frame = balanced_frame.sort_values(["sentiment_label", "id"], kind="stable").reset_index(drop=True)
    balanced_counts = balanced_frame["sentiment_name"].value_counts().to_dict()
    print(f"[stats] final balanced sentiment counts: {balanced_counts}")

    return merged_frame, balanced_frame


def split_balanced_dataframe_by_class(
    balanced_frame: pd.DataFrame,
    train_ratio: float = 0.80,
    validation_ratio: float = 0.10,
    test_ratio: float = 0.10,
) -> dict[str, pd.DataFrame]:
    if round(train_ratio + validation_ratio + test_ratio, 6) != 1.0:
        raise ValueError("train/validation/test ratios must sum to 1.0")

    split_parts = {
        "train": [],
        "validation": [],
        "test": [],
    }

    for sentiment_label in sorted(balanced_frame["sentiment_label"].unique()):
        class_frame = balanced_frame[balanced_frame["sentiment_label"] == sentiment_label].reset_index(drop=True)
        count = len(class_frame)
        train_end = int(round(count * train_ratio))
        validation_end = train_end + int(round(count * validation_ratio))

        # Keep the exact total by assigning remainder to test.
        split_parts["train"].append(class_frame.iloc[:train_end].copy())
        split_parts["validation"].append(class_frame.iloc[train_end:validation_end].copy())
        split_parts["test"].append(class_frame.iloc[validation_end:].copy())

    result = {}
    for split_name, parts in split_parts.items():
        split_frame = pd.concat(parts, ignore_index=True)
        split_frame = split_frame.sort_values(["sentiment_label", "id"], kind="stable").reset_index(drop=True)
        split_counts = split_frame["sentiment_name"].value_counts().to_dict()
        print(f"[stats] balanced {split_name} counts: {split_counts}")
        result[split_name] = split_frame

    return result


def main() -> None:
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)

    print(f"[info] dataset: {DATASET_NAME}")
    print("[info] fetching split names from Hugging Face...")
    split_names = get_dataset_split_names(DATASET_NAME)
    print(f"[info] available splits: {split_names}")

    dataset_dict = {}
    for split_name in split_names:
        print(f"[load] split='{split_name}'")
        dataset = load_dataset(DATASET_NAME, split=split_name)
        print(f"[load] rows in '{split_name}': {len(dataset):,}")
        dataset_dict[split_name] = dataset

    merged_dataset = DatasetDict(dataset_dict)

    os.makedirs(output_dir, exist_ok=True)
    print(f"[save] saving dataset to: {output_dir}")
    merged_dataset.save_to_disk(output_dir)

    for split_name, split_dataset in merged_dataset.items():
        csv_path = os.path.join(output_dir, f"{split_name}.csv")
        print(f"[save] exporting CSV for split='{split_name}' -> {csv_path}")
        split_dataset.to_csv(csv_path, index=False)

    print("[process] building balanced sentiment view...")
    merged_frame, balanced_frame = build_balanced_sentiment_dataframe(merged_dataset)
    balanced_splits = split_balanced_dataframe_by_class(balanced_frame)

    merged_csv_path = os.path.join(output_dir, "merged_all.csv")
    balanced_csv_path = os.path.join(output_dir, "balanced_all.csv")
    print(f"[save] exporting merged CSV -> {merged_csv_path}")
    merged_frame.to_csv(merged_csv_path, index=False)
    print(f"[save] exporting balanced CSV -> {balanced_csv_path}")
    balanced_frame.to_csv(balanced_csv_path, index=False)

    for split_name, split_frame in balanced_splits.items():
        split_csv_path = os.path.join(output_dir, f"balanced_{split_name}.csv")
        print(f"[save] exporting balanced split='{split_name}' -> {split_csv_path}")
        split_frame.to_csv(split_csv_path, index=False)

    print("[done] dataset saved successfully in Arrow, raw CSV, and balanced sentiment CSV formats.")


if __name__ == "__main__":
    main()
