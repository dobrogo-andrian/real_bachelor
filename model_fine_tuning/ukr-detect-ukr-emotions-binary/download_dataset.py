"""
Download and process the Hugging Face dataset:
    ukr-detect/ukr-emotions-binary

This script:
    1. Downloads all available splits.
    2. Maps the 6 emotion columns to 3-class sentiment (Negative, Neutral, Positive).
    3. Balances the classes (downsamples to the minority class).
    4. Shuffles all rows.
    5. Saves a SINGLE unified dataset as a CSV.
    6. Optionally saves Hugging Face save_to_disk() artifacts when explicitly requested.

Usage examples:
    python download_dataset.py
    python download_dataset.py --output-dir ".\\hf_saved_dataset"
"""

from __future__ import annotations

import argparse
import os

import pandas as pd
from datasets import get_dataset_split_names, load_dataset

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
    parser = argparse.ArgumentParser(description="Download and unify ukr-detect/ukr-emotions-binary locally.")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(".", "hf_saved_dataset"),
        help="Directory where the unified dataset will be saved.",
    )
    parser.add_argument(
        "--save-hf-dataset",
        action="store_true",
        help="Also export Hugging Face save_to_disk() artifacts. Disabled by default to avoid Arrow metadata files.",
    )
    return parser.parse_args()


def map_emotions_to_sentiment(row: pd.Series) -> int:
    """Maps the 6 emotion flags to a single 3-class sentiment integer."""
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


def build_unified_balanced_dataframe(dataset_dict: dict) -> pd.DataFrame:
    """Merges all splits, maps sentiments, balances classes, and shuffles."""
    split_frames = []
    for split_name, split_dataset in dataset_dict.items():
        frame = split_dataset.to_pandas()
        split_frames.append(frame)

    # 1. Merge all splits into one
    merged_frame = pd.concat(split_frames, ignore_index=True)

    # 2. Apply the emotion -> sentiment mapping
    print("[process] mapping emotions to 3-class sentiment...")
    merged_frame["label"] = merged_frame.apply(map_emotions_to_sentiment, axis=1)
    merged_frame["sentiment_name"] = merged_frame["label"].map(LABEL_NAMES)

    class_counts = merged_frame["sentiment_name"].value_counts().to_dict()
    print(f"[stats] raw mapped sentiment counts: {class_counts}")

    # 3. Find the minority class count to balance the dataset
    target_per_class = int(min(class_counts.values()))
    print(f"[stats] balancing dataset to {target_per_class:,} rows per class...")

    # 4. Downsample each class to match the minority class
    balanced_parts = []
    for sentiment_label in LABEL_NAMES.keys():
        class_frame = merged_frame[merged_frame["label"] == sentiment_label]
        # Randomly sample the exact number of needed rows
        sampled_frame = class_frame.sample(n=target_per_class, random_state=42)
        balanced_parts.append(sampled_frame)

    # 5. Combine and thoroughly shuffle the final dataset
    balanced_frame = pd.concat(balanced_parts, ignore_index=True)
    balanced_frame = balanced_frame.sample(frac=1, random_state=42).reset_index(drop=True)

    balanced_counts = balanced_frame["sentiment_name"].value_counts().to_dict()
    print(f"[stats] final balanced & shuffled counts: {balanced_counts}")

    return balanced_frame


def save_balanced_dataset_exports(frame: pd.DataFrame, output_dir: str, save_hf_dataset: bool) -> None:
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, "full_balanced_dataset.csv")
    print(f"[save] exporting unified CSV -> {csv_path}")
    frame.to_csv(csv_path, index=False)

    if not save_hf_dataset:
        print("[save] skipped Hugging Face save_to_disk() export.")
        return

    from datasets import Dataset

    unified_dataset = Dataset.from_pandas(frame, preserve_index=False)
    print(f"[save] saving unified dataset to: {output_dir}")
    unified_dataset.save_to_disk(output_dir)


def main() -> None:
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)

    print(f"[info] dataset: {DATASET_NAME}")
    print("[info] fetching split names from Hugging Face...")
    split_names = get_dataset_split_names(DATASET_NAME)
    print(f"[info] available splits: {split_names}")

    # Load all splits
    dataset_dict = {}
    for split_name in split_names:
        print(f"[load] loading split='{split_name}'...")
        dataset = load_dataset(DATASET_NAME, split=split_name)
        dataset_dict[split_name] = dataset

    # Process into a single, balanced, shuffled Pandas DataFrame
    balanced_frame = build_unified_balanced_dataframe(dataset_dict)

    save_balanced_dataset_exports(balanced_frame, output_dir, save_hf_dataset=args.save_hf_dataset)
    print("[done] unified dataset saved successfully.")


if __name__ == "__main__":
    main()
