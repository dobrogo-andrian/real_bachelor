"""
Memory-efficient LoRA fine-tuning script for multilingual sentiment analysis.

This script fine-tunes only LoRA adapters on top of:
    cardiffnlp/twitter-xlm-roberta-base-sentiment

Expected CSV schema:
    text: str
    label: int (0=Negative, 1=Neutral, 2=Positive)

Example:
    python model_fine_tuning/train_lora_sentiment.py ^
        --csv-path model_fine_tuning/balanced_sentiment_dataset/balanced_dataset.csv
"""

from __future__ import annotations

import argparse
import math
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import torch
from datasets import DatasetDict, load_dataset
from peft import LoraConfig, PeftModel, TaskType, get_peft_model
from sklearn.metrics import accuracy_score, f1_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    PreTrainedTokenizerBase,
    Trainer,
    TrainingArguments,
    set_seed,
)


MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_CSV_PATH = Path("model_fine_tuning/balanced_sentiment_dataset/balanced_dataset.csv")
DEFAULT_OUTPUT_DIR = Path("./sentiment_lora_adapters")
TEXT_COLUMN = "text"
LABEL_COLUMN = "label"
MAX_LENGTH = 128
SEED = 42

ID2LABEL = {
    0: "Negative",
    1: "Neutral",
    2: "Positive",
}
LABEL2ID = {label_name: label_id for label_id, label_name in ID2LABEL.items()}

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", flags=re.IGNORECASE)
MENTION_PATTERN = re.compile(r"@\w+")


@dataclass
class ScriptConfig:
    csv_path: Path
    output_dir: Path
    model_name: str
    max_length: int
    seed: int
    num_train_epochs: float
    learning_rate: float
    weight_decay: float
    per_device_train_batch_size: int
    per_device_eval_batch_size: int
    gradient_accumulation_steps: int
    eval_strategy: str
    save_strategy: str
    logging_steps: int
    eval_steps: int | None
    save_steps: int | None
    warmup_ratio: float


@dataclass(frozen=True)
class PrecisionConfig:
    fp16: bool
    bf16: bool
    pad_to_multiple_of: int | None
    accelerator_name: str


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fine-tune XLM-R sentiment classification with LoRA adapters on a balanced CSV dataset."
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH, help="Path to the balanced_dataset.csv file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where LoRA adapter weights and tokenizer will be saved.",
    )
    parser.add_argument("--model-name", default=MODEL_NAME, help="Base Hugging Face model ID.")
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH, help="Maximum tokenized sequence length.")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed for splitting and training.")
    parser.add_argument("--num-train-epochs", type=float, default=3.0, help="Number of training epochs.")
    parser.add_argument("--learning-rate", type=float, default=2e-4, help="Learning rate for LoRA adapters.")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="Weight decay.")
    parser.add_argument(
        "--per-device-train-batch-size",
        type=int,
        default=8,
        help="Small batch size to reduce GPU memory usage.",
    )
    parser.add_argument(
        "--per-device-eval-batch-size",
        type=int,
        default=8,
        help="Evaluation batch size.",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=4,
        help="Accumulate gradients to simulate a larger effective batch size.",
    )
    parser.add_argument("--eval-strategy", choices=["epoch", "steps"], default="epoch", help="Evaluation schedule.")
    parser.add_argument("--save-strategy", choices=["epoch", "steps"], default="epoch", help="Checkpoint schedule.")
    parser.add_argument("--logging-steps", type=int, default=25, help="Trainer logging interval.")
    parser.add_argument("--eval-steps", type=int, default=None, help="Evaluation interval when using step-based evaluation.")
    parser.add_argument("--save-steps", type=int, default=None, help="Checkpoint interval when using step-based saving.")
    parser.add_argument("--warmup-ratio", type=float, default=0.05, help="Warmup ratio.")
    return parser


def parse_args() -> ScriptConfig:
    args = build_arg_parser().parse_args()
    return ScriptConfig(
        csv_path=args.csv_path,
        output_dir=args.output_dir,
        model_name=args.model_name,
        max_length=args.max_length,
        seed=args.seed,
        num_train_epochs=args.num_train_epochs,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        eval_strategy=args.eval_strategy,
        save_strategy=args.save_strategy,
        logging_steps=args.logging_steps,
        eval_steps=args.eval_steps,
        save_steps=args.save_steps,
        warmup_ratio=args.warmup_ratio,
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )




def resolve_input_path(path: Path) -> Path:
    if path.is_absolute():
        return path

    candidates = [
        Path.cwd() / path,
        PROJECT_ROOT / path,
        SCRIPT_DIR / path,
        SCRIPT_DIR / path.name,
        PROJECT_ROOT / "model_fine_tuning" / "balanced_sentiment_dataset" / path.name,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return (Path.cwd() / path).resolve()


def resolve_output_path(path: Path) -> Path:
    if path.is_absolute():
        return path

    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.parent.exists():
        return cwd_candidate

    return (PROJECT_ROOT / path).resolve()


def validate_environment(config: ScriptConfig) -> None:
    config.csv_path = resolve_input_path(config.csv_path)
    config.output_dir = resolve_output_path(config.output_dir)

    if not config.csv_path.exists():
        raise FileNotFoundError(f"Dataset CSV was not found: {config.csv_path}")

    if config.max_length <= 0:
        raise ValueError("--max-length must be positive.")

    if config.per_device_train_batch_size <= 0 or config.per_device_eval_batch_size <= 0:
        raise ValueError("Batch sizes must be positive integers.")

    if config.gradient_accumulation_steps <= 0:
        raise ValueError("--gradient-accumulation-steps must be positive.")

def resolve_precision_config() -> PrecisionConfig:
    if torch.cuda.is_available():
        bf16_supported = bool(getattr(torch.cuda, "is_bf16_supported", lambda: False)())
        if bf16_supported:
            return PrecisionConfig(fp16=False, bf16=True, pad_to_multiple_of=8, accelerator_name="cuda-bf16")
        return PrecisionConfig(fp16=True, bf16=False, pad_to_multiple_of=8, accelerator_name="cuda-fp16")
    return PrecisionConfig(fp16=False, bf16=False, pad_to_multiple_of=None, accelerator_name="cpu")


def resolve_step_intervals(config: ScriptConfig) -> tuple[int | None, int | None]:
    if config.eval_strategy != "steps" and config.save_strategy != "steps":
        return None, None

    eval_steps = config.eval_steps if config.eval_strategy == "steps" else None
    save_steps = config.save_steps if config.save_strategy == "steps" else None

    default_steps = max(config.logging_steps, 1)
    if eval_steps is None and config.eval_strategy == "steps":
        eval_steps = save_steps or default_steps
    if save_steps is None and config.save_strategy == "steps":
        save_steps = eval_steps or default_steps

    if eval_steps is not None and eval_steps <= 0:
        raise ValueError("--eval-steps must be positive when eval-strategy=steps.")
    if save_steps is not None and save_steps <= 0:
        raise ValueError("--save-steps must be positive when save-strategy=steps.")
    if eval_steps is not None and save_steps is not None and save_steps % eval_steps != 0:
        raise ValueError("--save-steps must be a round multiple of --eval-steps when load_best_model_at_end is enabled.")

    return eval_steps, save_steps


def calculate_warmup_steps(train_dataset_size: int, config: ScriptConfig) -> int:
    if train_dataset_size <= 0:
        return 0

    effective_batch = max(config.per_device_train_batch_size * config.gradient_accumulation_steps, 1)
    steps_per_epoch = max(math.ceil(train_dataset_size / effective_batch), 1)
    total_training_steps = max(math.ceil(steps_per_epoch * config.num_train_epochs), 1)
    return max(int(total_training_steps * config.warmup_ratio), 0)


def normalize_social_text(text: str) -> str:
    """Match CardiffNLP social text normalization for URLs and mentions."""
    text = URL_PATTERN.sub("http", text)
    text = MENTION_PATTERN.sub("@user", text)
    return text.strip()


def preprocess_batch(batch: dict[str, list[Any]]) -> dict[str, list[Any]]:
    batch[TEXT_COLUMN] = [normalize_social_text(str(text)) for text in batch[TEXT_COLUMN]]
    return batch


def validate_columns(dataset: DatasetDict) -> None:
    required_columns = {TEXT_COLUMN, LABEL_COLUMN}
    train_columns = set(dataset["train"].column_names)
    missing = required_columns.difference(train_columns)
    if missing:
        missing_values = ", ".join(sorted(missing))
        raise ValueError(f"CSV is missing required columns: {missing_values}")


def validate_labels(dataset: DatasetDict) -> None:
    labels = set(dataset["train"][LABEL_COLUMN]) | set(dataset["validation"][LABEL_COLUMN])
    if labels != {0, 1, 2}:
        raise ValueError(f"Expected labels {{0, 1, 2}}, but found: {sorted(labels)}")


def load_and_split_dataset(csv_path: Path, seed: int) -> DatasetDict:
    logging.info("Loading dataset from %s", csv_path)
    dataset = load_dataset("csv", data_files=str(csv_path))["train"]
    split_dataset = dataset.train_test_split(test_size=0.10, seed=seed)
    dataset_dict = DatasetDict(
        {
            "train": split_dataset["train"],
            "validation": split_dataset["test"],
        }
    )
    validate_columns(dataset_dict)

    logging.info("Applying social-text normalization via dataset.map()")
    dataset_dict = dataset_dict.map(
        preprocess_batch,
        batched=True,
        desc="Normalizing URLs and mentions",
    )
    validate_labels(dataset_dict)

    logging.info(
        "Dataset ready: train=%s rows | validation=%s rows",
        len(dataset_dict["train"]),
        len(dataset_dict["validation"]),
    )
    return dataset_dict


def build_tokenizer(model_name: str) -> PreTrainedTokenizerBase:
    logging.info("Loading tokenizer: %s", model_name)
    tokenizer = AutoTokenizer.from_pretrained(
        pretrained_model_name_or_path=model_name,
        use_fast=True,
    )
    if not isinstance(tokenizer, PreTrainedTokenizerBase):
        raise TypeError(f"Loaded tokenizer has unexpected type: {type(tokenizer)!r}")
    return tokenizer


def tokenize_dataset(
    dataset: DatasetDict,
    tokenizer: PreTrainedTokenizerBase,
    max_length: int,
) -> DatasetDict:
    logging.info("Tokenizing with truncation and max_length=%s", max_length)

    def tokenize_batch(batch: dict[str, list[Any]]) -> dict[str, Any]:
        encoded_batch = tokenizer(
            text=batch[TEXT_COLUMN],
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        return dict(encoded_batch)

    tokenized = dataset.map(
        tokenize_batch,
        batched=True,
        desc="Tokenizing",
    )
    tokenized = tokenized.remove_columns([TEXT_COLUMN])
    return tokenized


def build_model(model_name: str) -> PeftModel:
    logging.info("Loading base model: %s", model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        revision="refs/pr/15"
    )

    # Gradient checkpointing reduces activation memory at the cost of extra compute.
    model.gradient_checkpointing_enable()

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        inference_mode=False,
        r=16,
        lora_alpha=32,
        lora_dropout=0.1,
        target_modules=["query", "value"],
        modules_to_save=["classifier"],
        bias="none",
    )

    model = cast(PeftModel, get_peft_model(model, lora_config))
    model.print_trainable_parameters()
    return model


def compute_metrics(eval_pred) -> dict[str, float]:
    predictions = eval_pred.predictions
    if isinstance(predictions, tuple):
        predictions = predictions[0]
    labels = eval_pred.label_ids
    predictions = np.argmax(predictions, axis=-1)
    return {
        "accuracy": accuracy_score(labels, predictions),
        "f1_macro": f1_score(labels, predictions, average="macro"),
    }


def build_training_arguments(config: ScriptConfig, precision: PrecisionConfig, train_dataset_size: int) -> TrainingArguments:
    output_dir = str(config.output_dir / "trainer_artifacts")
    logging.info("Preparing Trainer arguments with memory-saving settings")
    eval_steps, save_steps = resolve_step_intervals(config)
    warmup_steps = calculate_warmup_steps(train_dataset_size, config)
    return TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=config.num_train_epochs,
        learning_rate=config.learning_rate,
        weight_decay=config.weight_decay,
        per_device_train_batch_size=config.per_device_train_batch_size,
        per_device_eval_batch_size=config.per_device_eval_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        eval_strategy=config.eval_strategy,
        save_strategy=config.save_strategy,
        logging_strategy="steps",
        logging_steps=config.logging_steps,
        eval_steps=eval_steps,
        save_steps=save_steps,
        fp16=precision.fp16,
        bf16=precision.bf16,
        gradient_checkpointing=True,
        warmup_steps=warmup_steps,
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        save_total_limit=2,
        report_to="none",
        seed=config.seed,
        data_seed=config.seed,
        remove_unused_columns=False,
    )


def train_and_save(config: ScriptConfig) -> None:
    set_seed(config.seed)
    dataset = load_and_split_dataset(config.csv_path, config.seed)
    tokenizer = build_tokenizer(config.model_name)
    tokenized_dataset = tokenize_dataset(dataset, tokenizer, config.max_length)
    model = build_model(config.model_name)
    precision = resolve_precision_config()

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer, pad_to_multiple_of=precision.pad_to_multiple_of)
    training_args = build_training_arguments(config, precision, len(tokenized_dataset["train"]))

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["validation"],
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    logging.info("=" * 80)
    logging.info("--- BASELINE METRICS (BEFORE FINE-TUNING) ---")
    logging.info("=" * 80)
    baseline_metrics = trainer.evaluate()
    logging.info("Baseline metrics: %s", baseline_metrics)

    logging.info("=" * 80)
    logging.info("Starting training")
    logging.info("=" * 80)
    train_result = trainer.train()
    logging.info("Training complete. Final train metrics: %s", train_result.metrics)

    logging.info("=" * 80)
    logging.info("--- FINE-TUNED METRICS (AFTER FINE-TUNING) ---")
    logging.info("=" * 80)
    eval_metrics = trainer.evaluate()
    logging.info("Fine-tuned metrics: %s", eval_metrics)

    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Save only the PEFT adapter weights, not the full base model.
    logging.info("Saving LoRA adapters to %s", config.output_dir)
    trainer.model.save_pretrained(str(config.output_dir))

    logging.info("Saving tokenizer to %s", config.output_dir)
    tokenizer.save_pretrained(str(config.output_dir))

    logging.info("Saved adapter-only artifacts successfully")
    logging.info("=" * 80)
    logging.info("--- IMPROVEMENT SUMMARY ---")
    logging.info("=" * 80)

    baseline_accuracy = float(baseline_metrics.get("eval_accuracy", 0.0))
    baseline_f1 = float(baseline_metrics.get("eval_f1_macro", 0.0))
    fine_tuned_accuracy = float(eval_metrics.get("eval_accuracy", 0.0))
    fine_tuned_f1 = float(eval_metrics.get("eval_f1_macro", 0.0))

    accuracy_improvement = fine_tuned_accuracy - baseline_accuracy
    f1_improvement = fine_tuned_f1 - baseline_f1

    logging.info("Baseline Accuracy: %.4f", baseline_accuracy)
    logging.info("Fine-Tuned Accuracy: %.4f", fine_tuned_accuracy)
    logging.info("Accuracy Improvement: %+0.2f%%", accuracy_improvement * 100.0)
    logging.info("Baseline F1-Macro: %.4f", baseline_f1)
    logging.info("Fine-Tuned F1-Macro: %.4f", fine_tuned_f1)
    logging.info("F1-Macro Improvement: %+0.2f%%", f1_improvement * 100.0)
    logging.info("=" * 80)


def main() -> None:
    configure_logging()

    try:
        config = parse_args()
        validate_environment(config)
        logging.info("Using dataset: %s", config.csv_path.resolve())
        logging.info("Adapter output directory: %s", config.output_dir.resolve())
        precision = resolve_precision_config()
        logging.info(
            "Runtime settings: accelerator=%s | fp16=%s | bf16=%s | gradient_checkpointing=True | train_batch=%s | grad_accum=%s | max_length=%s",
            precision.accelerator_name,
            precision.fp16,
            precision.bf16,
            config.per_device_train_batch_size,
            config.gradient_accumulation_steps,
            config.max_length,
        )
        train_and_save(config)
        logging.info("All done")
    except KeyboardInterrupt:
        logging.error("Training interrupted by user.")
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("Training failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
