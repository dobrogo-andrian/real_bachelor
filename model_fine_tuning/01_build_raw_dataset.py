"""
Stage 1:
Build one unified raw dataset with standardized columns:
    text
    label

The output is saved to disk as a Hugging Face DatasetDict:
    train
    validation
"""

from __future__ import annotations

import os

from common import build_unified_dataset, parse_config


def main() -> None:
    config = parse_config("Stage 1: build unified raw sentiment dataset")
    dataset_dict = build_unified_dataset(config)

    os.makedirs(config.raw_output_dir, exist_ok=True)
    dataset_dict.save_to_disk(config.raw_output_dir)
    print(f"[done] raw unified dataset saved to: {config.raw_output_dir}")


if __name__ == "__main__":
    main()
