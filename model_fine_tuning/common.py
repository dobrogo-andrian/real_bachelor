"""
Shared utilities for the three-stage fine-tuning pipeline.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import pandas as pd
from datasets import Dataset, DatasetDict, concatenate_datasets, get_dataset_split_names, load_dataset
from sklearn.metrics import accuracy_score, f1_score


MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
NEGATIVE = 0
NEUTRAL = 1
POSITIVE = 2
LABEL_NAMES = {
    NEGATIVE: "negative",
    NEUTRAL: "neutral",
    POSITIVE: "positive",
}


@dataclass
class DatasetSpec:
    name: str
    source: str
    split: Optional[str]
    loader: Callable[["PipelineConfig"], Dataset]


@dataclass
class PipelineConfig:
    raw_output_dir: str
    processed_output_dir: str
    adapter_output_dir: str
    slang_source: Optional[str]
    slang_split: Optional[str]
    slang_text_column: str
    slang_label_column: str
    max_length: int
    per_device_train_batch_size: int
    per_device_eval_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    num_train_epochs: float
    warmup_ratio: float
    weight_decay: float
    eval_strategy: str
    save_strategy: str
    logging_steps: int
    eval_steps: Optional[int]
    save_steps: Optional[int]
    seed: int


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--raw-output-dir", default="./model_fine_tuning/artifacts/raw_dataset")
    parser.add_argument("--processed-output-dir", default="./model_fine_tuning/artifacts/processed_dataset")
    parser.add_argument("--adapter-output-dir", default="./model_fine_tuning/artifacts/lora_adapters")
    parser.add_argument("--slang-source", default=None, help="Optional local CSV path or Hugging Face dataset ID.")
    parser.add_argument("--slang-split", default=None)
    parser.add_argument("--slang-text-column", default="text")
    parser.add_argument("--slang-label-column", default="label")
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--per-device-train-batch-size", type=int, default=4)
    parser.add_argument("--per-device-eval-batch-size", type=int, default=8)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--num-train-epochs", type=float, default=3.0)
    parser.add_argument("--warmup-ratio", type=float, default=0.05)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--eval-strategy", choices=["epoch", "steps"], default="epoch")
    parser.add_argument("--save-strategy", choices=["epoch", "steps"], default="epoch")
    parser.add_argument("--logging-steps", type=int, default=50)
    parser.add_argument("--eval-steps", type=int, default=None)
    parser.add_argument("--save-steps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def parse_config(description: str) -> PipelineConfig:
    args = build_arg_parser(description).parse_args()
    return PipelineConfig(
        raw_output_dir=args.raw_output_dir,
        processed_output_dir=args.processed_output_dir,
        adapter_output_dir=args.adapter_output_dir,
        slang_source=args.slang_source,
        slang_split=args.slang_split,
        slang_text_column=args.slang_text_column,
        slang_label_column=args.slang_label_column,
        max_length=args.max_length,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        num_train_epochs=args.num_train_epochs,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        eval_strategy=args.eval_strategy,
        save_strategy=args.save_strategy,
        logging_steps=args.logging_steps,
        eval_steps=args.eval_steps,
        save_steps=args.save_steps,
        seed=args.seed,
    )


def bitsandbytes_available() -> bool:
    return importlib.util.find_spec("bitsandbytes") is not None


def pick_first_existing_column(columns: Iterable[str], candidates: Iterable[str], dataset_name: str) -> str:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    raise ValueError(f"[{dataset_name}] Could not find any of the expected columns: {list(candidates)}")


def pick_preferred_split(dataset_name: str, requested_split: Optional[str] = None) -> str:
    split_names = get_dataset_split_names(dataset_name)
    if requested_split:
        if requested_split not in split_names:
            raise ValueError(f"[{dataset_name}] Requested split '{requested_split}' not found. Available: {split_names}")
        return requested_split

    for preferred in ("train", "training", "full", "dataset"):
        if preferred in split_names:
            return preferred

    if not split_names:
        raise ValueError(f"[{dataset_name}] No splits were found.")

    return split_names[0]


def normalize_example(
    example: dict,
    text_key: str,
    label_key: str,
    map_label_fn: Callable[[object], Optional[int]],
) -> dict:
    text = str(example[text_key]).strip() if example.get(text_key) is not None else ""
    mapped_label = map_label_fn(example.get(label_key))
    return {
        "text": text,
        "label": mapped_label,
    }


def finalize_unified_dataset(dataset: Dataset, dataset_name: str) -> Dataset:
    dataset = dataset.filter(lambda row: bool(row["text"]) and row["label"] is not None)
    dataset = dataset.map(lambda row: {"label": int(row["label"])}, desc=f"Casting labels for {dataset_name}")
    print(f"[{dataset_name}] usable rows after normalization: {len(dataset):,}")
    return dataset


def map_rusentiment_label(raw_label: object) -> Optional[int]:
    value = str(raw_label).strip().lower()
    mapping = {
        "negative": NEGATIVE,
        "neutral": NEUTRAL,
        "positive": POSITIVE,
        "speech": None,
        "skip": None,
        "skip_speech": None,
        "unknown": None,
    }
    return mapping.get(value)


def map_ukr_emotions_row(example: dict) -> Optional[int]:
    """
    Convert binary emotion labels to 3-class sentiment.

    Rules:
    - Any negative emotion (Fear, Anger, Sadness, Disgust) => negative
    - Joy without negative emotions => positive
    - Surprise only => neutral
    - No active emotions => neutral
    - Joy mixed with any negative emotion => negative
    """
    joy = int(example.get("Joy", 0) or 0)
    fear = int(example.get("Fear", 0) or 0)
    anger = int(example.get("Anger", 0) or 0)
    sadness = int(example.get("Sadness", 0) or 0)
    disgust = int(example.get("Disgust", 0) or 0)
    surprise = int(example.get("Surprise", 0) or 0)

    has_negative = any([fear, anger, sadness, disgust])
    if has_negative:
        return NEGATIVE
    if joy:
        return POSITIVE
    if surprise:
        return NEUTRAL
    return NEUTRAL


def map_multilingual_label(raw_label: object) -> Optional[int]:
    value = str(raw_label).strip().lower()
    mapping = {
        "0": NEGATIVE,
        "1": NEUTRAL,
        "2": POSITIVE,
        "negative": NEGATIVE,
        "neutral": NEUTRAL,
        "positive": POSITIVE,
    }
    return mapping.get(value)


def map_slang_label(raw_label: object) -> Optional[int]:
    value = str(raw_label).strip().lower()
    mapping = {
        "negative": NEGATIVE,
        "neutral": NEUTRAL,
        "positive": POSITIVE,
        "sarcastic": NEGATIVE,
        "0": NEGATIVE,
        "1": NEUTRAL,
        "2": POSITIVE,
        "3": NEGATIVE,
    }
    return mapping.get(value)


def load_and_standardize_hf_dataset(
    dataset_name: str,
    split: Optional[str],
    text_candidates: Iterable[str],
    label_candidates: Iterable[str],
    map_label_fn: Callable[[object], Optional[int]],
) -> Dataset:
    chosen_split = pick_preferred_split(dataset_name, split)
    raw_dataset = load_dataset(dataset_name, split=chosen_split)

    text_key = pick_first_existing_column(raw_dataset.column_names, text_candidates, dataset_name)
    label_key = pick_first_existing_column(raw_dataset.column_names, label_candidates, dataset_name)

    print(f"[{dataset_name}] split='{chosen_split}', text='{text_key}', label='{label_key}', raw rows={len(raw_dataset):,}")

    normalized = raw_dataset.map(
        lambda row: normalize_example(row, text_key, label_key, map_label_fn),
        remove_columns=raw_dataset.column_names,
        desc=f"Normalizing {dataset_name}",
    )
    return finalize_unified_dataset(normalized, dataset_name)


def load_rusentiment(_: PipelineConfig) -> Dataset:
    return load_and_standardize_hf_dataset(
        dataset_name="sismetanin/rusentiment",
        split=None,
        text_candidates=("text", "sentence", "comment", "tweet"),
        label_candidates=("label", "sentiment"),
        map_label_fn=map_rusentiment_label,
    )


def load_ukr_emotions(_: PipelineConfig) -> Dataset:
    dataset_name = "ukr-detect/ukr-emotions-binary"
    chosen_split = pick_preferred_split(dataset_name, None)
    raw_dataset = load_dataset(dataset_name, split=chosen_split)
    text_key = pick_first_existing_column(raw_dataset.column_names, ("text", "sentence", "comment"), dataset_name)

    print(f"[{dataset_name}] split='{chosen_split}', text='{text_key}', raw rows={len(raw_dataset):,}")

    normalized = raw_dataset.map(
        lambda row: {
            "text": str(row[text_key]).strip() if row.get(text_key) is not None else "",
            "label": map_ukr_emotions_row(row),
        },
        remove_columns=raw_dataset.column_names,
        desc=f"Normalizing {dataset_name}",
    )
    return finalize_unified_dataset(normalized, dataset_name)


def load_multilingual_baseline(_: PipelineConfig) -> Dataset:
    return load_and_standardize_hf_dataset(
        dataset_name="cardiffnlp/tweet_sentiment_multilingual",
        split=None,
        text_candidates=("text", "tweet", "sentence"),
        label_candidates=("label", "sentiment"),
        map_label_fn=map_multilingual_label,
    )


def load_slang_dataset(config: PipelineConfig) -> Dataset:
    if not config.slang_source:
        raise ValueError("slang_source is not configured.")

    source = config.slang_source
    if os.path.isfile(source):
        frame = pd.read_csv(source)
        if config.slang_text_column not in frame.columns:
            raise ValueError(f"[slang local csv] Missing text column '{config.slang_text_column}'. Available: {list(frame.columns)}")
        if config.slang_label_column not in frame.columns:
            raise ValueError(f"[slang local csv] Missing label column '{config.slang_label_column}'. Available: {list(frame.columns)}")

        dataset = Dataset.from_pandas(frame, preserve_index=False)
        dataset_name = f"local_csv:{os.path.basename(source)}"
        text_key = config.slang_text_column
        label_key = config.slang_label_column
        print(f"[{dataset_name}] text='{text_key}', label='{label_key}', raw rows={len(dataset):,}")
    else:
        dataset_name = source
        chosen_split = pick_preferred_split(source, config.slang_split)
        dataset = load_dataset(source, split=chosen_split)
        text_key = pick_first_existing_column(dataset.column_names, (config.slang_text_column, "text", "comment"), dataset_name)
        label_key = pick_first_existing_column(dataset.column_names, (config.slang_label_column, "label", "sentiment"), dataset_name)
        print(f"[{dataset_name}] split='{chosen_split}', text='{text_key}', label='{label_key}', raw rows={len(dataset):,}")

    normalized = dataset.map(
        lambda row: normalize_example(row, text_key, label_key, map_slang_label),
        remove_columns=dataset.column_names,
        desc="Normalizing slang dataset",
    )
    return finalize_unified_dataset(normalized, "slang_dataset")


def build_unified_dataset(config: PipelineConfig) -> DatasetDict:
    dataset_specs = [
        DatasetSpec(name="rusentiment", source="sismetanin/rusentiment", split=None, loader=load_rusentiment),
        DatasetSpec(name="ukr_emotions_binary", source="ukr-detect/ukr-emotions-binary", split=None, loader=load_ukr_emotions),
        DatasetSpec(name="tweet_sentiment_multilingual", source="cardiffnlp/tweet_sentiment_multilingual", split=None, loader=load_multilingual_baseline),
    ]

    if config.slang_source:
        dataset_specs.append(
            DatasetSpec(name="slang_dataset", source=config.slang_source, split=config.slang_split, loader=load_slang_dataset)
        )
    else:
        print("[slang_dataset] skipped because --slang-source was not provided.")

    normalized_datasets = [spec.loader(config) for spec in dataset_specs]
    merged = concatenate_datasets(normalized_datasets)
    merged = merged.shuffle(seed=config.seed)

    print(f"[merged] total rows after concatenation: {len(merged):,}")

    split_dataset = merged.train_test_split(test_size=0.10, seed=config.seed)
    print(f"[split] train rows: {len(split_dataset['train']):,}")
    print(f"[split] valid rows: {len(split_dataset['test']):,}")

    return DatasetDict({
        "train": split_dataset["train"],
        "validation": split_dataset["test"],
    })


def compute_metrics(eval_pred) -> dict:
    logits, labels = eval_pred
    predictions = logits.argmax(axis=-1)
    return {
        "accuracy": accuracy_score(labels, predictions),
        "f1_macro": f1_score(labels, predictions, average="macro"),
    }
