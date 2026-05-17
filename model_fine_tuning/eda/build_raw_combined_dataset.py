from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model_fine_tuning.prepare_and_balance_data import (
    build_label_distribution,
    load_file_to_dataframe,
    standardize_dataframe,
)


SOURCE_CONFIG = [
    {
        "source": "russian_twitter",
        "path": Path("model_fine_tuning/sismetanin-rusentitweet-blob-main-rusentitweet-full/rusentitweet_full.csv"),
    },
    {
        "source": "english_twitter",
        "path": Path("model_fine_tuning/Sp1786-multiclass-sentiment-analysis-dataset/hf_saved_dataset/full_dataset.csv"),
    },
    {
        "source": "ukrainian_emotions",
        "path": Path("model_fine_tuning/ukr-detect-ukr-emotions-binary/hf_saved_dataset/full_balanced_dataset.csv"),
    },
    {
        "source": "synthetic_slang_emoji",
        "path": Path("model_fine_tuning/symbols/slang_data.csv"),
    },
]


def parse_args() -> argparse.Namespace:
    default_project_root = Path(__file__).resolve().parents[2]
    default_output_dir = Path("model_fine_tuning/eda/data")
    parser = argparse.ArgumentParser(
        description=(
            "Build a unified sentiment dataset for EDA (labels mapped to 0/1/2), "
            "without duplicate removal and without balancing."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=default_project_root,
        help=f"Project root directory (default: {default_project_root}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where unified CSV and manifest will be saved.",
    )
    return parser.parse_args()


def print_distribution(title: str, frame: pd.DataFrame) -> None:
    label_stats = build_label_distribution(frame)
    print(f"\n{title}")
    print(f"  negative (0): {label_stats['negative']:,}")
    print(f"  neutral  (1): {label_stats['neutral']:,}")
    print(f"  positive (2): {label_stats['positive']:,}")
    print(f"  total       : {len(frame):,}")


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    output_dir = (project_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    standardized_frames: list[pd.DataFrame] = []
    source_details: list[dict[str, Any]] = []

    for item in SOURCE_CONFIG:
        source_name = item["source"]
        source_path = (project_root / item["path"]).resolve()

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        raw_frame = load_file_to_dataframe(source_path)
        standardized, provenance = standardize_dataframe(raw_frame, source_path)
        provenance["source"] = source_name
        source_details.append(provenance)

        if standardized.empty:
            continue

        standardized = standardized.copy()
        standardized["source"] = source_name
        standardized_frames.append(standardized[["text", "label", "source"]])

    if not standardized_frames:
        raise ValueError("No usable standardized rows were produced from configured sources.")

    combined = pd.concat(standardized_frames, ignore_index=True)
    combined["label"] = combined["label"].astype(int)

    output_csv = output_dir / "raw_combined_unbalanced_dataset.csv"
    combined.to_csv(output_csv, index=False, encoding="utf-8")

    manifest = {
        "dataset_name": "raw_combined_unbalanced_dataset",
        "note": "Unified dataset before cross-source duplicate removal and before strict random undersampling.",
        "output_csv": str(output_csv),
        "row_count": int(len(combined)),
        "class_distribution": build_label_distribution(combined),
        "source_distribution": {str(k): int(v) for k, v in combined["source"].value_counts().to_dict().items()},
        "source_files": source_details,
    }
    manifest_path = output_dir / "raw_combined_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[done] Raw combined dataset saved.")
    print(f"  CSV: {output_csv}")
    print(f"  Manifest: {manifest_path}")

    print_distribution("Class distribution in raw combined dataset", combined)
    print("\nSource distribution:")
    print(combined["source"].value_counts().to_string())


if __name__ == "__main__":
    main()
