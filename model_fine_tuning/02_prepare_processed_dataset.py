"""
Stage 2:
Load the raw unified dataset from disk, tokenize it, and save the processed dataset.
"""

from __future__ import annotations

import os

from datasets import load_from_disk
from transformers import AutoTokenizer

from common import MODEL_NAME, parse_config


def tokenize_dataset(dataset_dict, tokenizer, max_length: int):
    def tokenize_batch(batch: dict) -> dict:
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_length,
        )

    return dataset_dict.map(
        tokenize_batch,
        batched=True,
        desc="Tokenizing datasets",
    )


def main() -> None:
    config = parse_config("Stage 2: tokenize and save processed dataset")

    print(f"[load] reading raw dataset from: {config.raw_output_dir}")
    dataset_dict = load_from_disk(config.raw_output_dir)

    print("[setup] loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    print("[setup] tokenizing dataset...")
    tokenized_datasets = tokenize_dataset(dataset_dict, tokenizer, config.max_length)

    os.makedirs(config.processed_output_dir, exist_ok=True)
    tokenized_datasets.save_to_disk(config.processed_output_dir)
    tokenizer.save_pretrained(config.processed_output_dir)

    print(f"[done] processed dataset saved to: {config.processed_output_dir}")


if __name__ == "__main__":
    main()
