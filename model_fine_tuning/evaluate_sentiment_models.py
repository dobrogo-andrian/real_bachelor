"""
Evaluate the baseline CardiffNLP sentiment model against the fine-tuned LoRA model.

The script reuses the same dataset split and text preprocessing as the training pipeline,
then prints and optionally saves a comparison report for:
    - baseline zero-shot transformer
    - classic baselines (TF-IDF + Logistic Regression, TF-IDF + Linear SVM)
    - fine-tuned LoRA transformer
with:
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
import csv
import json
import logging
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from peft import PeftModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
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
DEFAULT_ARTIFACTS_DIR = Path("model_fine_tuning/artifacts/evaluation")
CLASS_LABELS = [0, 1, 2]
THESIS_CLASS_ORDER = ("Positive", "Neutral", "Negative")
CLASSIC_BASELINE_NAMES = ("tfidf_logreg", "tfidf_linear_svm")


@dataclass
class EvaluationConfig:
    csv_path: Path
    adapter_dir: Path
    report_path: Path | None
    artifacts_dir: Path
    trainer_state_path: Path | None
    skip_figures: bool
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
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help="Directory where thesis-oriented outputs (plots/tables) will be saved.",
    )
    parser.add_argument(
        "--trainer-state-path",
        type=Path,
        default=None,
        help="Optional direct path to trainer_state.json for loss-curve export. If omitted, the latest checkpoint is used.",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Disable saving PNG figures.",
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
        artifacts_dir=args.artifacts_dir,
        trainer_state_path=args.trainer_state_path,
        skip_figures=args.skip_figures,
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
    config.artifacts_dir = resolve_output_path(config.artifacts_dir)
    if config.trainer_state_path is not None:
        config.trainer_state_path = resolve_input_path(config.trainer_state_path)

    if not config.csv_path.exists():
        raise FileNotFoundError(f"Dataset CSV was not found: {config.csv_path}")
    if not config.adapter_dir.exists():
        raise FileNotFoundError(f"Adapter directory was not found: {config.adapter_dir}")
    if config.trainer_state_path is not None and not config.trainer_state_path.exists():
        raise FileNotFoundError(f"trainer_state.json was not found: {config.trainer_state_path}")
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


def load_text_split_dataset(config: EvaluationConfig) -> tuple[list[str], np.ndarray, list[str], np.ndarray]:
    dataset = load_and_split_dataset(config.csv_path, config.seed)
    train_dataset = dataset["train"]
    validation_dataset = dataset["validation"]
    x_train = [str(text) for text in train_dataset["text"]]
    y_train = np.array(train_dataset["label"], dtype=int)
    x_val = [str(text) for text in validation_dataset["text"]]
    y_val = np.array(validation_dataset["label"], dtype=int)
    return x_train, y_train, x_val, y_val


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


def _ensure_2d_scores(values: np.ndarray) -> np.ndarray:
    if values.ndim == 1:
        return values.reshape(-1, 1)
    return values


def _align_class_scores(scores: np.ndarray, model_classes: np.ndarray) -> np.ndarray:
    aligned = np.zeros((scores.shape[0], len(CLASS_LABELS)), dtype=float)
    for source_index, class_id in enumerate(model_classes):
        target_index = int(class_id)
        if target_index in CLASS_LABELS:
            aligned[:, target_index] = scores[:, source_index]
    return aligned


def _scores_from_classifier(classifier, x_val: list[str]) -> np.ndarray:
    if hasattr(classifier, "predict_proba"):
        scores = classifier.predict_proba(x_val)
        return _ensure_2d_scores(np.asarray(scores, dtype=float))

    if hasattr(classifier, "decision_function"):
        decision = classifier.decision_function(x_val)
        decision = _ensure_2d_scores(np.asarray(decision, dtype=float))
        if decision.shape[1] == 1:
            binary = np.hstack([-decision, decision])
            return _ensure_2d_scores(binary)
        return decision

    raise TypeError("Classifier must implement either predict_proba() or decision_function().")


def train_and_evaluate_classic_model(
    model_name: str,
    classifier_pipeline: Pipeline,
    x_train: list[str],
    y_train: np.ndarray,
    x_val: list[str],
    y_val: np.ndarray,
) -> dict[str, Any]:
    logging.info("Training classic baseline: %s", model_name)
    classifier_pipeline.fit(x_train, y_train)
    raw_scores = _scores_from_classifier(classifier_pipeline, x_val)
    model_classes = np.asarray(classifier_pipeline.classes_, dtype=int)
    class_aligned_scores = _align_class_scores(raw_scores, model_classes)
    probabilities = softmax(class_aligned_scores)
    metrics = compute_classification_metrics(y_val, probabilities)
    print_metrics_block(f"{model_name.upper()} METRICS", metrics)
    return metrics


def build_classic_baseline_pipelines(seed: int) -> dict[str, Pipeline]:
    return {
        "tfidf_logreg": Pipeline(
            steps=[
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=120_000, min_df=2)),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=2000,
                        multi_class="multinomial",
                        solver="lbfgs",
                        random_state=seed,
                    ),
                ),
            ]
        ),
        "tfidf_linear_svm": Pipeline(
            steps=[
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=120_000, min_df=2)),
                ("clf", LinearSVC(C=1.0, random_state=seed)),
            ]
        ),
    }


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


def build_fine_tuned_vs_classic_summary(
    fine_tuned_metrics: dict[str, Any],
    classic_metrics_by_name: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    comparable_metrics = ("accuracy", "precision_macro", "recall_macro", "f1_macro", "roc_auc_ovr_macro")
    summary: dict[str, dict[str, Any]] = {}
    for classic_name, classic_metrics in classic_metrics_by_name.items():
        per_model_summary: dict[str, Any] = {}
        for metric_name in comparable_metrics:
            classic_value = classic_metrics.get(metric_name)
            fine_tuned_value = fine_tuned_metrics.get(metric_name)
            per_model_summary[metric_name] = {
                "classic": classic_value,
                "fine_tuned": fine_tuned_value,
                "delta": None if classic_value is None or fine_tuned_value is None else float(fine_tuned_value - classic_value),
            }
        summary[classic_name] = per_model_summary
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
    print_per_class_table(title, metrics)


def print_per_class_table(title: str, metrics: dict[str, Any]) -> None:
    logging.info("%s | Per-class table (Precision/Recall/F1):", title)
    logging.info("| Class | Precision | Recall | F1-score | Support |")
    logging.info("|---|---:|---:|---:|---:|")
    for label_name in THESIS_CLASS_ORDER:
        label_metrics = metrics["per_class"].get(label_name)
        if label_metrics is None:
            continue
        logging.info(
            "| %s | %.4f | %.4f | %.4f | %s |",
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


def print_classic_comparison_summary(summary: dict[str, dict[str, Any]]) -> None:
    if not summary:
        return
    logging.info("=" * 80)
    logging.info("FINE-TUNED VS CLASSIC BASELINES SUMMARY")
    logging.info("=" * 80)
    for classic_name, model_summary in summary.items():
        logging.info("Classic model: %s", classic_name)
        for metric_name, metric_values in model_summary.items():
            classic_value = metric_values["classic"]
            fine_tuned_value = metric_values["fine_tuned"]
            delta = metric_values["delta"]
            if classic_value is None or fine_tuned_value is None or delta is None:
                logging.info("%s | classic=%s | fine_tuned=%s | delta=unavailable", metric_name, classic_value, fine_tuned_value)
                continue
            logging.info("%s | classic=%.4f | fine_tuned=%.4f | delta=%+.4f", metric_name, classic_value, fine_tuned_value, delta)


def save_report(report: dict[str, Any], report_path: Path | None) -> None:
    if report_path is None:
        return

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Saved evaluation report to %s", report_path)


def find_latest_trainer_state(adapter_dir: Path) -> Path | None:
    trainer_artifacts_dir = adapter_dir / "trainer_artifacts"
    if not trainer_artifacts_dir.exists():
        return None

    checkpoint_candidates = []
    for checkpoint_dir in trainer_artifacts_dir.glob("checkpoint-*"):
        if not checkpoint_dir.is_dir():
            continue
        try:
            checkpoint_step = int(checkpoint_dir.name.split("-")[-1])
        except ValueError:
            continue
        trainer_state = checkpoint_dir / "trainer_state.json"
        if trainer_state.exists():
            checkpoint_candidates.append((checkpoint_step, trainer_state))

    if not checkpoint_candidates:
        return None
    checkpoint_candidates.sort(key=lambda item: item[0], reverse=True)
    return checkpoint_candidates[0][1]


def extract_epoch_loss_rows(trainer_state: dict[str, Any]) -> list[dict[str, float | int | None]]:
    log_history = trainer_state.get("log_history", [])
    train_losses: dict[int, list[float]] = {}
    eval_losses: dict[int, float] = {}

    for item in log_history:
        if "epoch" not in item:
            continue
        epoch_value = float(item["epoch"])
        epoch_index = int(math.ceil(max(epoch_value, 1e-9)))
        if "loss" in item and isinstance(item["loss"], (int, float)):
            train_losses.setdefault(epoch_index, []).append(float(item["loss"]))
        if "eval_loss" in item and isinstance(item["eval_loss"], (int, float)):
            eval_losses[epoch_index] = float(item["eval_loss"])

    all_epochs = sorted(set(train_losses) | set(eval_losses))
    rows: list[dict[str, float | int | None]] = []
    for epoch_index in all_epochs:
        epoch_train_values = train_losses.get(epoch_index, [])
        rows.append(
            {
                "epoch": epoch_index,
                "train_loss": None if not epoch_train_values else float(np.mean(epoch_train_values)),
                "val_loss": eval_losses.get(epoch_index),
            }
        )
    return rows


def save_loss_rows_csv(rows: list[dict[str, float | int | None]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["epoch,train_loss,val_loss"]
    for row in rows:
        train_value = "" if row["train_loss"] is None else f"{float(row['train_loss']):.6f}"
        val_value = "" if row["val_loss"] is None else f"{float(row['val_loss']):.6f}"
        lines.append(f"{int(row['epoch'])},{train_value},{val_value}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("Saved epoch loss table to %s", output_path)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def save_evaluation_all_metrics_csv(
    output_path: Path,
    model_metrics_by_name: dict[str, dict[str, Any]],
    comparison_summary: dict[str, Any],
    classic_comparison_summary: dict[str, dict[str, Any]],
    loss_rows: list[dict[str, float | int | None]] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "record_type",
        "model",
        "metric",
        "class",
        "true_label",
        "pred_label",
        "epoch",
        "value",
        "baseline",
        "fine_tuned",
        "classic",
        "delta",
        "support",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()

        for model_name, metrics in model_metrics_by_name.items():
            for metric_name in ("sample_count", "accuracy", "precision_macro", "recall_macro", "f1_macro", "roc_auc_ovr_macro"):
                writer.writerow(
                    {
                        "record_type": "overall_metric",
                        "model": model_name,
                        "metric": metric_name,
                        "value": _csv_value(metrics.get(metric_name)),
                    }
                )

            per_class = metrics.get("per_class", {})
            for class_name in THESIS_CLASS_ORDER:
                class_metrics = per_class.get(class_name)
                if class_metrics is None:
                    continue
                for metric_name in ("precision", "recall", "f1"):
                    writer.writerow(
                        {
                            "record_type": "per_class_metric",
                            "model": model_name,
                            "class": class_name,
                            "metric": metric_name,
                            "value": _csv_value(class_metrics.get(metric_name)),
                            "support": _csv_value(class_metrics.get("support")),
                        }
                    )

            labels = metrics.get("labels", [])
            matrix = metrics.get("confusion_matrix", [])
            for true_index, row in enumerate(matrix):
                true_label = labels[true_index] if true_index < len(labels) else str(true_index)
                for pred_index, count in enumerate(row):
                    pred_label = labels[pred_index] if pred_index < len(labels) else str(pred_index)
                    writer.writerow(
                        {
                            "record_type": "confusion_matrix",
                            "model": model_name,
                            "true_label": true_label,
                            "pred_label": pred_label,
                            "value": _csv_value(count),
                        }
                    )

        for metric_name, values in comparison_summary.items():
            writer.writerow(
                {
                    "record_type": "zero_shot_vs_fine_tuned",
                    "metric": metric_name,
                    "baseline": _csv_value(values.get("baseline")),
                    "fine_tuned": _csv_value(values.get("fine_tuned")),
                    "delta": _csv_value(values.get("delta")),
                }
            )

        for classic_name, metrics_summary in classic_comparison_summary.items():
            for metric_name, values in metrics_summary.items():
                writer.writerow(
                    {
                        "record_type": "classic_vs_fine_tuned",
                        "model": classic_name,
                        "metric": metric_name,
                        "classic": _csv_value(values.get("classic")),
                        "fine_tuned": _csv_value(values.get("fine_tuned")),
                        "delta": _csv_value(values.get("delta")),
                    }
                )

        if loss_rows is not None:
            for row in loss_rows:
                writer.writerow(
                    {
                        "record_type": "loss_by_epoch",
                        "metric": "train_loss",
                        "epoch": _csv_value(row.get("epoch")),
                        "value": _csv_value(row.get("train_loss")),
                    }
                )
                writer.writerow(
                    {
                        "record_type": "loss_by_epoch",
                        "metric": "val_loss",
                        "epoch": _csv_value(row.get("epoch")),
                        "value": _csv_value(row.get("val_loss")),
                    }
                )
    logging.info("Saved consolidated metrics CSV to %s", output_path)


def _load_matplotlib():
    import matplotlib.pyplot as plt  # noqa: PLC0415

    return plt


def save_confusion_matrix_figure(metrics: dict[str, Any], output_path: Path) -> bool:
    try:
        plt = _load_matplotlib()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Skipping confusion matrix figure (matplotlib unavailable): %s", exc)
        return False

    matrix = np.array(metrics["confusion_matrix"], dtype=int)
    labels = metrics["labels"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 6))
    image = ax.imshow(matrix, interpolation="nearest", cmap="Blues")
    fig.colorbar(image, ax=ax)
    ax.set_title("Confusion Matrix (Fine-Tuned Model)")
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_yticklabels(labels)

    threshold = matrix.max() / 2 if matrix.size else 0.0
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            color = "white" if matrix[i, j] > threshold else "black"
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color=color, fontsize=10)

    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    logging.info("Saved confusion matrix figure to %s", output_path)
    return True


def save_loss_curve_figure(rows: list[dict[str, float | int | None]], output_path: Path) -> bool:
    try:
        plt = _load_matplotlib()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Skipping loss-curve figure (matplotlib unavailable): %s", exc)
        return False

    epochs: list[int] = []
    train_values: list[float] = []
    val_epochs: list[int] = []
    val_values: list[float] = []
    for row in rows:
        epoch = int(row["epoch"])
        train_loss = row["train_loss"]
        val_loss = row["val_loss"]
        if train_loss is not None:
            epochs.append(epoch)
            train_values.append(float(train_loss))
        if val_loss is not None:
            val_epochs.append(epoch)
            val_values.append(float(val_loss))

    if not epochs and not val_epochs:
        logging.warning("Skipping loss-curve figure: no train/eval loss points found in trainer_state.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    if epochs:
        ax.plot(epochs, train_values, marker="o", linewidth=2.0, label="Training loss (avg per epoch)")
    if val_epochs:
        ax.plot(val_epochs, val_values, marker="s", linewidth=2.0, label="Validation loss")
    ax.set_title("Loss per Epoch (Train vs Validation)")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.grid(alpha=0.25)
    ax.set_xticks(sorted(set(epochs + val_epochs)))
    ax.legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    logging.info("Saved loss curve figure to %s", output_path)
    return True


def export_thesis_artifacts(
    config: EvaluationConfig,
    model_metrics_by_name: dict[str, dict[str, Any]],
    fine_tuned_metrics: dict[str, Any],
    comparison_summary: dict[str, Any],
    classic_comparison_summary: dict[str, dict[str, Any]],
) -> dict[str, str]:
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    consolidated_csv = config.artifacts_dir / "evaluation_all_metrics.csv"

    confusion_matrix_png = config.artifacts_dir / "fine_tuned_confusion_matrix.png"
    if not config.skip_figures and save_confusion_matrix_figure(fine_tuned_metrics, confusion_matrix_png):
        outputs["confusion_matrix_figure"] = str(confusion_matrix_png)

    trainer_state_path = config.trainer_state_path or find_latest_trainer_state(config.adapter_dir)
    if trainer_state_path is None:
        logging.warning(
            "Loss-curve export skipped: trainer_state.json not found. Run training once to generate this artifact."
        )
        save_evaluation_all_metrics_csv(
            consolidated_csv,
            model_metrics_by_name,
            comparison_summary,
            classic_comparison_summary,
            loss_rows=None,
        )
        outputs["evaluation_all_metrics_csv"] = str(consolidated_csv)
        return outputs

    logging.info("Using trainer state for loss export: %s", trainer_state_path)
    trainer_state = json.loads(trainer_state_path.read_text(encoding="utf-8"))
    loss_rows = extract_epoch_loss_rows(trainer_state)
    if not loss_rows:
        logging.warning("Loss-curve export skipped: no epoch loss data found in trainer_state.json.")
        save_evaluation_all_metrics_csv(
            consolidated_csv,
            model_metrics_by_name,
            comparison_summary,
            classic_comparison_summary,
            loss_rows=None,
        )
        outputs["evaluation_all_metrics_csv"] = str(consolidated_csv)
        return outputs

    loss_curve_png = config.artifacts_dir / "loss_train_vs_val.png"
    if not config.skip_figures and save_loss_curve_figure(loss_rows, loss_curve_png):
        outputs["loss_curve_figure"] = str(loss_curve_png)

    save_evaluation_all_metrics_csv(
        consolidated_csv,
        model_metrics_by_name,
        comparison_summary,
        classic_comparison_summary,
        loss_rows=loss_rows,
    )
    outputs["evaluation_all_metrics_csv"] = str(consolidated_csv)

    return outputs


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

    x_train, y_train, x_val, y_val = load_text_split_dataset(config)
    classic_pipelines = build_classic_baseline_pipelines(config.seed)
    classic_metrics_by_name: dict[str, dict[str, Any]] = {}
    for classic_name in CLASSIC_BASELINE_NAMES:
        pipeline = classic_pipelines[classic_name]
        classic_metrics_by_name[classic_name] = train_and_evaluate_classic_model(
            classic_name,
            pipeline,
            x_train,
            y_train,
            x_val,
            y_val,
        )

    comparison_summary = build_comparison_summary(baseline_metrics, fine_tuned_metrics)
    print_comparison_summary(comparison_summary)
    classic_comparison_summary = build_fine_tuned_vs_classic_summary(fine_tuned_metrics, classic_metrics_by_name)
    print_classic_comparison_summary(classic_comparison_summary)
    all_model_metrics = {
        "baseline_zero_shot": baseline_metrics,
        **classic_metrics_by_name,
        "fine_tuned_lora": fine_tuned_metrics,
    }
    thesis_artifacts = export_thesis_artifacts(
        config,
        all_model_metrics,
        fine_tuned_metrics,
        comparison_summary,
        classic_comparison_summary,
    )

    if thesis_artifacts:
        logging.info("Thesis artifacts generated:")
        for artifact_name, artifact_path in thesis_artifacts.items():
            logging.info("  %s: %s", artifact_name, artifact_path)

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
        "classic_baselines": {
            classic_name: {"metrics": metrics} for classic_name, metrics in classic_metrics_by_name.items()
        },
        "comparison_summary": comparison_summary,
        "classic_comparison_summary": classic_comparison_summary,
        "thesis_artifacts": thesis_artifacts,
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
