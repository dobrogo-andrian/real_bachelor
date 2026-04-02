"""
Download and save the Hugging Face dataset:
    Sp1786/multiclass-sentiment-analysis-dataset

This script downloads all available splits (train, test, validation, etc.),
concatenates them into a SINGLE unified dataset, shuffles the rows,
and saves:
    1. A single readable CSV file containing all rows.
    2. Optionally, Hugging Face save_to_disk() artifacts when explicitly requested.

Usage examples:
    python download_dataset.py
    python download_dataset.py --output-dir ".\\hf_saved_dataset"
"""

from __future__ import annotations

import argparse
import os

from datasets import concatenate_datasets, get_dataset_split_names, load_dataset


DATASET_NAME = "Sp1786/multiclass-sentiment-analysis-dataset"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and unify Sp1786/multiclass-sentiment-analysis-dataset locally."
    )
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


def save_unified_dataset_exports(unified_dataset, output_dir: str, save_hf_dataset: bool) -> None:
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, "full_dataset.csv")
    print(f"[save] exporting unified CSV -> {csv_path}")
    unified_dataset.to_csv(csv_path, index=False)

    if not save_hf_dataset:
        print("[save] skipped Hugging Face save_to_disk() export.")
        return

    print(f"[save] saving unified dataset to: {output_dir}")
    unified_dataset.save_to_disk(output_dir)


def main() -> None:
    args = parse_args()
    output_dir = os.path.abspath(args.output_dir)

    print(f"[info] dataset: {DATASET_NAME}")
    print("[info] fetching split names from Hugging Face...")

    # Get all splits (e.g., ['train', 'validation', 'test'])
    split_names = get_dataset_split_names(DATASET_NAME)
    print(f"[info] available splits: {split_names}")

    all_splits = []

    # Load each split and append it to our list
    for split_name in split_names:
        print(f"[load] loading split='{split_name}'...")
        dataset = load_dataset(DATASET_NAME, split=split_name)
        print(f"[load] rows in '{split_name}': {len(dataset):,}")
        all_splits.append(dataset)

    # Concatenate all splits into one single dataset
    print("[process] concatenating all splits into a single dataset...")
    unified_dataset = concatenate_datasets(all_splits)

    # Shuffle the dataset so train/test/val rows are thoroughly mixed
    print("[process] shuffling the unified dataset...")
    unified_dataset = unified_dataset.shuffle(seed=42)

    print(f"[info] total rows in unified dataset: {len(unified_dataset):,}")

    save_unified_dataset_exports(unified_dataset, output_dir, save_hf_dataset=args.save_hf_dataset)
    print("[done] unified dataset saved successfully.")


if __name__ == "__main__":
    main()
