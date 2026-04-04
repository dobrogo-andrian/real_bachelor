"""
Evaluate the baseline CardiffNLP sentiment model against the fine-tuned LoRA model.

The script reuses the same dataset split and text preprocessing as the training pipeline,
then prints and optionally saves a comparison report with:
    - accuracy
    - precision / recall / f1 (macro + per class)
    - confusion matrix
    - ROC-AUC (macro OVR, when available)

Example:
    python model_fine_tuning/evaluate_sentiment_models.py ^
        --csv-path model_fine_tuning/balanced_sentiment_dataset/balanced_dataset.csv ^
        --adapter-dir model_fine_tuning/sentiment_lora_adapters
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from peft import PeftModel
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, DataCollatorWithPadding

from model_fine_tuning.train_lora_sentiment import (
    DEFAULT_CSV_PATH,
    ID2LABEL,
    LABEL2ID,
    MAX_LENGTH,
    MODEL_NAME,
    SEED,
    build_tokenizer,
    load_and_split_dataset,
    resolve_input_path,
    resolve_output_path,
    tokenize_dataset,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ADAPTER_DIR = Path("model_fine_tuning/sentiment_lora_adapters")
DEFAULT_REPORT_PATH = Path("model_fine_tuning/artifacts/evaluation/model_comparison.json")
CLASS_LABELS = [0, 1, 2]


@dataclass
class EvaluationConfig:
    csv_path: Path
    adapter_dir: Path
    report_path: Path | None
    model_name: str
    max_length: int
    seed: int
    batch_size: int


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate baseline and fine-tuned multilingual sentiment models on the same validation split."
    )
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH, help="Path to the evaluation CSV dataset.")
    parser.add_argument(
        "--adapter-dir",
        type=Path,
        default=DEFAULT_ADAPTER_DIR,
        help="Directory with saved LoRA adapter weights and tokenizer.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Optional JSON output path for the comparison report. Use --report-path '' to disable saving.",
    )
    parser.add_argument("--model-name", default=MODEL_NAME, help="Base Hugging Face model ID.")
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH, help="Maximum tokenized sequence length.")
    parser.add_argument("--seed", type=int, default=SEED, help="Seed used to reproduce the validation split.")
    parser.add_argument("--batch-size", type=int, default=16, help="Evaluation batch size.")
    return parser


def parse_args() -> EvaluationConfig:
    args = build_arg_parser().parse_args()
    report_path = args.report_path if str(args.report_path).strip() else None
    return EvaluationConfig(
        csv_path=args.csv_path,
        adapter_dir=args.adapter_dir,
        report_path=report_path,
        model_name=args.model_name,
        max_length=args.max_length,
        seed=args.seed,
        batch_size=args.batch_size,
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def validate_environment(config: EvaluationConfig) -> None:
    config.csv_path = resolve_input_path(config.csv_path)
    config.adapter_dir = resolve_input_path(config.adapter_dir)
    if config.report_path is not None:
        config.report_path = resolve_output_path(config.report_path)

    if not config.csv_path.exists():
        raise FileNotFoundError(f"Dataset CSV was not found: {config.csv_path}")
    if not config.adapter_dir.exists():
        raise FileNotFoundError(f"Adapter directory was not found: {config.adapter_dir}")
    if config.batch_size <= 0:
        raise ValueError("--batch-size must be positive.")
    if config.max_length <= 0:
        raise ValueError("--max-length must be positive.")


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_validation_dataset(config: EvaluationConfig):
    dataset = load_and_split_dataset(config.csv_path, config.seed)
    tokenizer = build_tokenizer(config.model_name)
    tokenized_dataset = tokenize_dataset(dataset, tokenizer, config.max_length)
    return tokenizer, tokenized_dataset["validation"]


def load_baseline_model(model_name: str):
    logging.info("Loading baseline model: %s", model_name)
    return AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        revision="refs/pr/15",
    )


def load_fine_tuned_model(model_name: str, adapter_dir: Path):
    logging.info("Loading fine-tuned model from adapters: %s", adapter_dir)
    base_model = load_baseline_model(model_name)
    peft_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    merged_model = peft_model.merge_and_unload()
    return merged_model


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp_values = np.exp(shifted)
    return exp_values / exp_values.sum(axis=1, keepdims=True)


def run_model_inference(model, tokenized_dataset, tokenizer, batch_size: int, device: torch.device) -> tuple[np.ndarray, np.ndarray]:
    model.to(device)
    model.eval()

    collator = DataCollatorWithPadding(tokenizer=tokenizer, pad_to_multiple_of=8 if device.type == "cuda" else None)
    dataloader = DataLoader(tokenized_dataset, batch_size=batch_size, shuffle=False, collate_fn=collator)

    all_probabilities: list[np.ndarray] = []
    all_labels: list[np.ndarray] = []

    for batch in dataloader:
        labels = batch.pop("labels").detach().cpu().numpy()
        batch = {key: value.to(device) for key, value in batch.items()}
        with torch.no_grad():
            outputs = model(**batch)
        logits = outputs.logits.detach().cpu().numpy()
        probabilities = softmax(logits)

        all_probabilities.append(probabilities)
        all_labels.append(labels)

    return np.concatenate(all_labels), np.concatenate(all_probabilities)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def compute_classification_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predictions = probabilities.argmax(axis=1)
    precision_per_class, recall_per_class, f1_per_class, support_per_class = precision_recall_fscore_support(
        y_true,
        predictions,
        labels=CLASS_LABELS,
        average=None,
        zero_division=0,
    )
    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true,
        predictions,
        average="macro",
        zero_division=0,
    )

    try:
        roc_auc_macro_ovr = roc_auc_score(y_true, probabilities, labels=CLASS_LABELS, multi_class="ovr", average="macro")
    except ValueError:
        roc_auc_macro_ovr = None

    per_class = {}
    for index, label_id in enumerate(CLASS_LABELS):
        label_name = ID2LABEL[label_id]
        per_class[label_name] = {
            "precision": float(precision_per_class[index]),
            "recall": float(recall_per_class[index]),
            "f1": float(f1_per_class[index]),
            "support": int(support_per_class[index]),
        }

    return {
        "sample_count": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "precision_macro": float(precision_macro),
        "recall_macro": float(recall_macro),
        "f1_macro": float(f1_macro),
        "roc_auc_ovr_macro": _safe_float(roc_auc_macro_ovr),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=CLASS_LABELS).astype(int).tolist(),
        "labels": [ID2LABEL[label_id] for label_id in CLASS_LABELS],
        "per_class": per_class,
    }


def build_comparison_summary(baseline_metrics: dict[str, Any], fine_tuned_metrics: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    comparable_metrics = ("accuracy", "precision_macro", "recall_macro", "f1_macro", "roc_auc_ovr_macro")
    for metric_name in comparable_metrics:
        baseline_value = baseline_metrics.get(metric_name)
        fine_tuned_value = fine_tuned_metrics.get(metric_name)
        summary[metric_name] = {
            "baseline": baseline_value,
            "fine_tuned": fine_tuned_value,
            "delta": None if baseline_value is None or fine_tuned_value is None else float(fine_tuned_value - baseline_value),
        }
    return summary


def print_metrics_block(title: str, metrics: dict[str, Any]) -> None:
    logging.info("=" * 80)
    logging.info("%s", title)
    logging.info("=" * 80)
    logging.info("Samples: %s", metrics["sample_count"])
    logging.info("Accuracy: %.4f", metrics["accuracy"])
    logging.info("Precision (macro): %.4f", metrics["precision_macro"])
    logging.info("Recall (macro): %.4f", metrics["recall_macro"])
    logging.info("F1 (macro): %.4f", metrics["f1_macro"])
    if metrics["roc_auc_ovr_macro"] is None:
        logging.info("ROC-AUC (macro, OVR): unavailable for the current label distribution")
    else:
        logging.info("ROC-AUC (macro, OVR): %.4f", metrics["roc_auc_ovr_macro"])

    logging.info("Confusion matrix [rows=true, cols=pred] for labels %s:", ", ".join(metrics["labels"]))
    for row in metrics["confusion_matrix"]:
        logging.info("%s", row)

    for label_name, label_metrics in metrics["per_class"].items():
        logging.info(
            "Class %-8s | precision=%.4f | recall=%.4f | f1=%.4f | support=%s",
            label_name,
            label_metrics["precision"],
            label_metrics["recall"],
            label_metrics["f1"],
            label_metrics["support"],
        )


def print_comparison_summary(summary: dict[str, Any]) -> None:
    logging.info("=" * 80)
    logging.info("MODEL COMPARISON SUMMARY")
    logging.info("=" * 80)
    for metric_name, metric_values in summary.items():
        baseline_value = metric_values["baseline"]
        fine_tuned_value = metric_values["fine_tuned"]
        delta = metric_values["delta"]
        if baseline_value is None or fine_tuned_value is None or delta is None:
            logging.info("%s | baseline=%s | fine_tuned=%s | delta=unavailable", metric_name, baseline_value, fine_tuned_value)
            continue
        logging.info("%s | baseline=%.4f | fine_tuned=%.4f | delta=%+.4f", metric_name, baseline_value, fine_tuned_value, delta)


def save_report(report: dict[str, Any], report_path: Path | None) -> None:
    if report_path is None:
        return

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Saved evaluation report to %s", report_path)


def evaluate_models(config: EvaluationConfig) -> dict[str, Any]:
    tokenizer, validation_dataset = load_validation_dataset(config)
    device = get_device()
    logging.info("Using evaluation device: %s", device)
    logging.info("Validation samples: %s", len(validation_dataset))

    baseline_model = load_baseline_model(config.model_name)
    baseline_labels, baseline_probabilities = run_model_inference(
        baseline_model,
        validation_dataset,
        tokenizer,
        config.batch_size,
        device,
    )
    baseline_metrics = compute_classification_metrics(baseline_labels, baseline_probabilities)
    print_metrics_block("BASELINE MODEL METRICS", baseline_metrics)

    fine_tuned_model = load_fine_tuned_model(config.model_name, config.adapter_dir)
    fine_tuned_labels, fine_tuned_probabilities = run_model_inference(
        fine_tuned_model,
        validation_dataset,
        tokenizer,
        config.batch_size,
        device,
    )
    fine_tuned_metrics = compute_classification_metrics(fine_tuned_labels, fine_tuned_probabilities)
    print_metrics_block("FINE-TUNED MODEL METRICS", fine_tuned_metrics)

    if not np.array_equal(baseline_labels, fine_tuned_labels):
        raise ValueError("Baseline and fine-tuned evaluations used different label orderings.")

    comparison_summary = build_comparison_summary(baseline_metrics, fine_tuned_metrics)
    print_comparison_summary(comparison_summary)

    return {
        "dataset": {
            "csv_path": str(config.csv_path),
            "validation_sample_count": int(len(validation_dataset)),
            "seed": config.seed,
            "max_length": config.max_length,
        },
        "baseline_model": {
            "model_name": config.model_name,
            "metrics": baseline_metrics,
        },
        "fine_tuned_model": {
            "model_name": config.model_name,
            "adapter_dir": str(config.adapter_dir),
            "metrics": fine_tuned_metrics,
        },
        "comparison_summary": comparison_summary,
    }


def main() -> None:
    configure_logging()
    try:
        config = parse_args()
        validate_environment(config)
        report = evaluate_models(config)
        save_report(report, config.report_path)
        logging.info("Evaluation complete")
    except KeyboardInterrupt:
        logging.error("Evaluation interrupted by user.")
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("Evaluation failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
