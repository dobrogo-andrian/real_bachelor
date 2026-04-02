"""
Prepare one unified, strictly balanced sentiment dataset for fine-tuning.

This script:
1. Recursively scans a root directory for local dataset files (ignores HF metadata).
2. Loads CSV, JSON/JSONL, and Parquet files with pandas.
3. Standardizes every dataset into exactly two columns:
       text  -> str
       label -> int (0=negative, 1=neutral, 2=positive)
4. Drops unusable rows (missing text, empty text, unknown labels).
5. Strictly balances the three classes by random undersampling.
6. Shuffles the final dataset.
7. Saves a readable CSV version of the final balanced dataset.
8. Optionally saves a Hugging Face disk dataset when explicitly requested.

Example:
    python model_fine_tuning/prepare_and_balance_data.py \
        --input-dir ./model_fine_tuning \
        --output-dir ./balanced_sentiment_dataset \
        --seed 42
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
NEGATIVE = 0
NEUTRAL = 1
POSITIVE = 2
ALLOWED_LABELS = {NEGATIVE, NEUTRAL, POSITIVE}

SUPPORTED_EXTENSIONS = {".csv", ".json", ".jsonl", ".parquet"}
TEXT_COLUMN_CANDIDATES = (
    "text",
    "tweet",
    "sentence",
    "comment",
    "content",
    "review",
    "message",
    "post",
    "body",
)
LABEL_COLUMN_CANDIDATES = (
    "label",
    "labels",
    "sentiment",
    "sentiment_name",
    "class",
    "target",
    "polarity",
    "stance",
)
EMOTION_COLUMNS = ("Joy", "Fear", "Anger", "Sadness", "Disgust", "Surprise")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load local sentiment datasets, unify them, strictly balance classes, and save as a HF Dataset."
    )
    parser.add_argument(
        "--input-dir",
        default="./",
        help="Main directory that contains the downloaded dataset subfolders.",
    )
    parser.add_argument(
        "--output-dir",
        default="./balanced_sentiment_dataset",
        help="Directory where the balanced dataset exports will be saved.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used for reproducible undersampling and shuffling.",
    )
    parser.add_argument(
        "--save-hf-dataset",
        action="store_true",
        help="Also export Hugging Face save_to_disk() artifacts. Disabled by default to avoid Arrow metadata files.",
    )
    return parser


def find_data_files(root_dir: Path) -> list[Path]:
    """Recursively discover supported data files, ignoring Hugging Face metadata files."""
    ignore_files = {"dataset_info.json", "state.json", "dataset_dict.json"}
    files = [
        path
        for path in root_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and path.name not in ignore_files
    ]
    return sorted(files)


def load_file_to_dataframe(file_path: Path) -> pd.DataFrame:
    """Load one supported file into a pandas DataFrame."""
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(file_path)

    if suffix == ".parquet":
        return pd.read_parquet(file_path)

    if suffix in {".json", ".jsonl"}:
        try:
            return pd.read_json(file_path, lines=suffix == ".jsonl")
        except ValueError:
            with file_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            if isinstance(payload, dict):
                return pd.json_normalize(payload)
            raise ValueError(f"Unsupported JSON structure in {file_path.name}")

    raise ValueError(f"Unsupported file type: {file_path.name}")


def pick_first_existing_column(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    normalized = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]
    return None


def infer_text_column(frame: pd.DataFrame) -> str:
    """Find the most likely text column for a dataset."""
    chosen = pick_first_existing_column(frame.columns, TEXT_COLUMN_CANDIDATES)
    if chosen:
        return chosen

    object_columns = [
        column
        for column in frame.columns
        if pd.api.types.is_string_dtype(frame[column]) or frame[column].dtype == object
    ]
    if not object_columns:
        raise ValueError("Could not infer a text column.")

    scored_columns = []
    for column in object_columns:
        series = frame[column].dropna().astype(str).str.strip()
        non_empty = series[series != ""]
        average_length = non_empty.str.len().mean() if not non_empty.empty else 0
        scored_columns.append((average_length, column))

    scored_columns.sort(reverse=True)
    guessed_col = scored_columns[0][1]

    print(f"  [warning] Guessed text column based on length: '{guessed_col}'")
    return guessed_col


def infer_label_column(frame: pd.DataFrame) -> Optional[str]:
    """Find a likely label column if one exists directly in the dataset."""
    chosen = pick_first_existing_column(frame.columns, LABEL_COLUMN_CANDIDATES)
    if chosen:
        return chosen

    for column in frame.columns:
        if column == infer_text_column(frame):
            continue

        series = frame[column].dropna()
        if series.empty:
            continue

        unique_values = {str(value).strip().lower() for value in series.unique()}
        if unique_values <= {
            "0", "1", "2", "3", "-1",
            "negative", "neutral", "positive", "neg", "neu", "pos",
            "mixed", "sarcastic", "speech", "skip", "skip_speech", "unknown",
            "позитивний", "негативний", "нейтральний" # Added Cyrillic checks
        }:
            return column

    return None


def map_emotion_row_to_sentiment(row: pd.Series) -> int:
    """Convert multi-hot emotion columns into 3-class sentiment."""
    joy = int(row.get("Joy", 0) or 0)
    fear = int(row.get("Fear", 0) or 0)
    anger = int(row.get("Anger", 0) or 0)
    sadness = int(row.get("Sadness", 0) or 0)
    disgust = int(row.get("Disgust", 0) or 0)
    surprise = int(row.get("Surprise", 0) or 0)

    has_negative = any([fear, anger, sadness, disgust])
    if has_negative:
        return NEGATIVE
    if joy:
        return POSITIVE
    if surprise:
        return NEUTRAL
    return NEUTRAL


def map_label_value(raw_label: object) -> Optional[int]:
    """Map heterogeneous raw labels into the standard 3-class label space."""
    if pd.isna(raw_label):
        return None

    if isinstance(raw_label, bool):
        return None

    if isinstance(raw_label, (int, float)) and not isinstance(raw_label, bool):
        numeric = int(raw_label)
        numeric_mapping = {
            -1: NEGATIVE,
            0: NEGATIVE,
            1: NEUTRAL,
            2: POSITIVE,
            3: NEGATIVE,
            4: None,
        }
        return numeric_mapping.get(numeric)

    value = str(raw_label).strip().lower()
    if not value:
        return None

    mapping = {
        "-1": NEGATIVE, "0": NEGATIVE, "1": NEUTRAL, "2": POSITIVE, "3": NEGATIVE, "4": None,
        "negative": NEGATIVE, "neg": NEGATIVE, "bad": NEGATIVE, "bearish": NEGATIVE,
        "neutral": NEUTRAL, "neu": NEUTRAL, "objective": NEUTRAL, "other": NEUTRAL,
        "positive": POSITIVE, "pos": POSITIVE, "good": POSITIVE, "bullish": POSITIVE,
        "mixed": NEGATIVE, "sarcastic": NEGATIVE, "irony": NEGATIVE, "ironic": NEGATIVE,
        "speech": None, "skip": None, "skip_speech": None, "unknown": None, "none": None, "nan": None,
        "позитивний": POSITIVE, "позитив": POSITIVE, "положительный": POSITIVE,
        "негативний": NEGATIVE, "негатив": NEGATIVE, "отрицательный": NEGATIVE,
        "нейтральний": NEUTRAL, "нейтраль": NEUTRAL, "нейтральный": NEUTRAL,
    }
    return mapping.get(value)


def standardize_dataframe(frame: pd.DataFrame, file_path: Path) -> pd.DataFrame:
    """Convert one dataset into the exact target schema: text + label."""
    initial_rows = len(frame)
    print(f"\n[process] Analyzing {file_path.name} ({initial_rows:,} rows)...")

    if frame.empty:
        print(f"  [skip] File is empty.")
        return pd.DataFrame(columns=["text", "label"])

    text_column = infer_text_column(frame)

    frame_cols_lower = {c.lower(): c for c in frame.columns}
    emotion_cols_lower = [c.lower() for c in EMOTION_COLUMNS]

    if all(col in frame_cols_lower for col in emotion_cols_lower):
        print(f"  [info] Detected Emotion columns. Mapping to 3-class sentiment.")
        rename_map = {frame_cols_lower[col]: col.capitalize() for col in emotion_cols_lower}
        temp_frame = frame.rename(columns=rename_map)
        standardized = pd.DataFrame(
            {
                "text": temp_frame[text_column],
                "label": temp_frame.apply(map_emotion_row_to_sentiment, axis=1),
            }
        )
    else:
        label_column = infer_label_column(frame)
        if label_column is None:
            print(f"  [skip] Could not infer a label column.")
            return pd.DataFrame(columns=["text", "label"])

        print(f"  [info] Mapped label column '{label_column}' to 3-class sentiment.")
        standardized = pd.DataFrame(
            {
                "text": frame[text_column],
                "label": frame[label_column].map(map_label_value),
            }
        )

    standardized["text"] = standardized["text"].fillna("").astype(str).str.strip()
    standardized = standardized[standardized["text"] != ""]
    standardized = standardized[standardized["label"].isin(ALLOWED_LABELS)]
    standardized["label"] = standardized["label"].astype(int)
    standardized = standardized.reset_index(drop=True)

    final_rows = len(standardized)
    dropped_rows = initial_rows - final_rows

    print(f"  [result] Kept {final_rows:,} rows (Dropped {dropped_rows:,} invalid/unmapped rows).")

    if final_rows > 0:
        counts = standardized["label"].value_counts().reindex([NEGATIVE, NEUTRAL, POSITIVE], fill_value=0)
        print(f"  [dist]   Neg: {counts[NEGATIVE]:,} | Neu: {counts[NEUTRAL]:,} | Pos: {counts[POSITIVE]:,}")

    return standardized


def print_class_distribution(frame: pd.DataFrame, title: str) -> None:
    """Print counts for each sentiment class in a consistent order."""
    counts = frame["label"].value_counts().reindex([NEGATIVE, NEUTRAL, POSITIVE], fill_value=0)
    print(f"\n{title}")
    print("-" * len(title))
    print(f"negative (0): {counts[NEGATIVE]:,}")
    print(f"neutral  (1): {counts[NEUTRAL]:,}")
    print(f"positive (2): {counts[POSITIVE]:,}")
    print(f"total       : {int(counts.sum()):,}")


def strictly_balance_classes(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Undersample every class down to the minority class size."""
    counts = frame["label"].value_counts()
    missing_labels = ALLOWED_LABELS.difference(counts.index.tolist())
    if missing_labels:
        missing = ", ".join(str(label) for label in sorted(missing_labels))
        raise ValueError(f"Cannot balance dataset because these labels are missing: {missing}")

    minority_count = int(counts.min())
    balanced_parts = []

    for label in sorted(ALLOWED_LABELS):
        label_frame = frame[frame["label"] == label]
        balanced_parts.append(label_frame.sample(n=minority_count, random_state=seed))

    balanced = pd.concat(balanced_parts, ignore_index=True)
    balanced = balanced.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return balanced


def save_balanced_dataset_exports(frame: pd.DataFrame, output_dir: Path, save_hf_dataset: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    export_frame = frame[["text", "label"]]
    csv_output_path = output_dir / "balanced_dataset.csv"
    export_frame.to_csv(csv_output_path, index=False, encoding="utf-8")
    print(f"[done] Balanced CSV dataset saved to: {csv_output_path}")

    if not save_hf_dataset:
        return

    from datasets import Dataset

    hf_dataset = Dataset.from_pandas(export_frame, preserve_index=False)
    hf_dataset.save_to_disk(str(output_dir))
    print(f"[done] Balanced Hugging Face dataset saved to: {output_dir}")


def main() -> None:
    args = build_arg_parser().parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    print(f"[scan] Input directory: {input_dir}")
    files = find_data_files(input_dir)
    if not files:
        raise FileNotFoundError(f"No supported data files were found under: {input_dir}")

    print(f"[scan] Discovered {len(files)} supported files.")

    standardized_frames = []
    for file_path in files:
        try:
            raw_frame = load_file_to_dataframe(file_path)
            standardized = standardize_dataframe(raw_frame, file_path)
            if not standardized.empty:
                standardized_frames.append(standardized)
        except Exception as exc:  # noqa: BLE001
            print(f"  [error] Failed to process {file_path.name}: {exc}")

    if not standardized_frames:
        raise ValueError("No usable rows were produced from the discovered files.")

    combined = pd.concat(standardized_frames, ignore_index=True)
    initial_combined_len = len(combined)

    combined = combined.drop_duplicates(subset=["text"]).reset_index(drop=True)

    duplicates_dropped = initial_combined_len - len(combined)
    print(f"\n[merge] Dropped {duplicates_dropped:,} duplicate texts across datasets.")
    print(f"[merge] Total usable unique rows: {len(combined):,}")

    print_class_distribution(combined, "Class distribution BEFORE balancing")

    balanced = strictly_balance_classes(combined, seed=args.seed)
    print_class_distribution(balanced, "Class distribution AFTER balancing")

    print()
    save_balanced_dataset_exports(balanced, output_dir, save_hf_dataset=args.save_hf_dataset)


if __name__ == "__main__":
    main()
