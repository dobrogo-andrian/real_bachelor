import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from model_fine_tuning import evaluate_sentiment_models as eval_module


class EvaluateSentimentModelsTests(unittest.TestCase):
    def test_compute_classification_metrics_includes_requested_metrics(self):
        y_true = np.array([0, 1, 2, 0, 1, 2])
        probabilities = np.array(
            [
                [0.90, 0.05, 0.05],
                [0.10, 0.80, 0.10],
                [0.05, 0.10, 0.85],
                [0.60, 0.20, 0.20],
                [0.15, 0.70, 0.15],
                [0.20, 0.30, 0.50],
            ]
        )

        metrics = eval_module.compute_classification_metrics(y_true, probabilities)

        self.assertEqual(metrics["sample_count"], 6)
        self.assertAlmostEqual(metrics["accuracy"], 1.0)
        self.assertAlmostEqual(metrics["precision_macro"], 1.0)
        self.assertAlmostEqual(metrics["recall_macro"], 1.0)
        self.assertAlmostEqual(metrics["f1_macro"], 1.0)
        self.assertIsNotNone(metrics["roc_auc_ovr_macro"])
        self.assertEqual(metrics["confusion_matrix"], [[2, 0, 0], [0, 2, 0], [0, 0, 2]])
        self.assertEqual(set(metrics["per_class"].keys()), {"Negative", "Neutral", "Positive"})

    def test_compute_classification_metrics_handles_unavailable_roc_auc(self):
        y_true = np.array([1, 1, 1])
        probabilities = np.array(
            [
                [0.10, 0.80, 0.10],
                [0.05, 0.90, 0.05],
                [0.20, 0.70, 0.10],
            ]
        )

        metrics = eval_module.compute_classification_metrics(y_true, probabilities)

        self.assertIsNone(metrics["roc_auc_ovr_macro"])
        self.assertEqual(metrics["confusion_matrix"], [[0, 0, 0], [0, 3, 0], [0, 0, 0]])

    def test_build_comparison_summary_calculates_deltas(self):
        baseline = {
            "accuracy": 0.50,
            "precision_macro": 0.51,
            "recall_macro": 0.52,
            "f1_macro": 0.53,
            "roc_auc_ovr_macro": 0.54,
        }
        fine_tuned = {
            "accuracy": 0.70,
            "precision_macro": 0.71,
            "recall_macro": 0.72,
            "f1_macro": 0.73,
            "roc_auc_ovr_macro": 0.74,
        }

        summary = eval_module.build_comparison_summary(baseline, fine_tuned)

        self.assertAlmostEqual(summary["accuracy"]["delta"], 0.20)
        self.assertAlmostEqual(summary["precision_macro"]["delta"], 0.20)
        self.assertAlmostEqual(summary["recall_macro"]["delta"], 0.20)
        self.assertAlmostEqual(summary["f1_macro"]["delta"], 0.20)
        self.assertAlmostEqual(summary["roc_auc_ovr_macro"]["delta"], 0.20)

    def test_build_fine_tuned_vs_classic_summary_calculates_deltas(self):
        fine_tuned = {
            "accuracy": 0.8,
            "precision_macro": 0.81,
            "recall_macro": 0.82,
            "f1_macro": 0.83,
            "roc_auc_ovr_macro": 0.84,
        }
        classic = {
            "tfidf_logreg": {
                "accuracy": 0.6,
                "precision_macro": 0.61,
                "recall_macro": 0.62,
                "f1_macro": 0.63,
                "roc_auc_ovr_macro": 0.64,
            }
        }

        summary = eval_module.build_fine_tuned_vs_classic_summary(fine_tuned, classic)

        self.assertAlmostEqual(summary["tfidf_logreg"]["accuracy"]["delta"], 0.2)
        self.assertAlmostEqual(summary["tfidf_logreg"]["f1_macro"]["delta"], 0.2)

    def test_load_fine_tuned_model_merges_lora_adapters(self):
        fake_base_model = object()

        class FakePeftModel:
            def merge_and_unload(self):
                return "merged-model"

        with patch.object(eval_module, "load_baseline_model", return_value=fake_base_model), patch.object(
            eval_module.PeftModel,
            "from_pretrained",
            return_value=FakePeftModel(),
        ) as from_pretrained:
            merged_model = eval_module.load_fine_tuned_model("model-name", Path("adapter-dir"))

        self.assertEqual(merged_model, "merged-model")
        from_pretrained.assert_called_once_with(fake_base_model, "adapter-dir")

    def test_extract_epoch_loss_rows_aggregates_train_and_eval(self):
        trainer_state = {
            "log_history": [
                {"epoch": 0.20, "loss": 2.0, "step": 25},
                {"epoch": 0.80, "loss": 1.0, "step": 100},
                {"epoch": 1.00, "eval_loss": 0.9, "step": 120},
                {"epoch": 1.30, "loss": 0.8, "step": 140},
                {"epoch": 2.00, "eval_loss": 0.7, "step": 200},
            ]
        }

        rows = eval_module.extract_epoch_loss_rows(trainer_state)

        self.assertEqual(rows, [{"epoch": 1, "train_loss": 1.5, "val_loss": 0.9}, {"epoch": 2, "train_loss": 0.8, "val_loss": 0.7}])

    def test_find_latest_trainer_state_prefers_max_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter_dir = Path(tmp_dir)
            ckpt_10 = adapter_dir / "trainer_artifacts" / "checkpoint-10"
            ckpt_20 = adapter_dir / "trainer_artifacts" / "checkpoint-20"
            ckpt_10.mkdir(parents=True, exist_ok=True)
            ckpt_20.mkdir(parents=True, exist_ok=True)
            (ckpt_10 / "trainer_state.json").write_text(json.dumps({"id": 10}), encoding="utf-8")
            (ckpt_20 / "trainer_state.json").write_text(json.dumps({"id": 20}), encoding="utf-8")

            latest = eval_module.find_latest_trainer_state(adapter_dir)

        self.assertEqual(latest.name, "trainer_state.json")
        self.assertEqual(latest.parent.name, "checkpoint-20")

    def test_save_evaluation_all_metrics_csv_writes_expected_file(self):
        baseline_metrics = {
            "sample_count": 6,
            "accuracy": 0.5,
            "precision_macro": 0.51,
            "recall_macro": 0.52,
            "f1_macro": 0.53,
            "roc_auc_ovr_macro": 0.54,
            "labels": ["Negative", "Neutral", "Positive"],
            "confusion_matrix": [[1, 1, 0], [0, 1, 1], [1, 0, 1]],
            "per_class": {
                "Positive": {"precision": 0.70, "recall": 0.71, "f1": 0.72, "support": 2},
                "Neutral": {"precision": 0.60, "recall": 0.61, "f1": 0.62, "support": 2},
                "Negative": {"precision": 0.50, "recall": 0.51, "f1": 0.52, "support": 2},
            },
        }
        fine_tuned_metrics = {
            "sample_count": 6,
            "accuracy": 0.8,
            "precision_macro": 0.81,
            "recall_macro": 0.82,
            "f1_macro": 0.83,
            "roc_auc_ovr_macro": 0.84,
            "labels": ["Negative", "Neutral", "Positive"],
            "confusion_matrix": [[2, 0, 0], [0, 2, 0], [0, 0, 2]],
            "per_class": {
                "Positive": {"precision": 0.90, "recall": 0.91, "f1": 0.92, "support": 2},
                "Neutral": {"precision": 0.80, "recall": 0.81, "f1": 0.82, "support": 2},
                "Negative": {"precision": 0.70, "recall": 0.71, "f1": 0.72, "support": 2},
            },
        }
        comparison_summary = {
            "accuracy": {"baseline": 0.5, "fine_tuned": 0.8, "delta": 0.3},
            "f1_macro": {"baseline": 0.53, "fine_tuned": 0.83, "delta": 0.3},
        }

        model_metrics_by_name = {
            "baseline_zero_shot": baseline_metrics,
            "tfidf_logreg": baseline_metrics,
            "tfidf_linear_svm": baseline_metrics,
            "fine_tuned_lora": fine_tuned_metrics,
        }
        classic_summary = {
            "tfidf_logreg": {
                "accuracy": {"classic": 0.5, "fine_tuned": 0.8, "delta": 0.3},
            }
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "evaluation_all_metrics.csv"
            eval_module.save_evaluation_all_metrics_csv(
                csv_path,
                model_metrics_by_name,
                comparison_summary,
                classic_summary,
                loss_rows=[{"epoch": 1, "train_loss": 1.2, "val_loss": 0.9}],
            )
            self.assertTrue(csv_path.exists())
            content = csv_path.read_text(encoding="utf-8")
            self.assertIn("record_type,model,metric", content)
            self.assertIn("overall_metric,baseline_zero_shot,accuracy", content)
            self.assertIn("per_class_metric,fine_tuned_lora,precision,Positive", content)
            self.assertIn("zero_shot_vs_fine_tuned,,accuracy", content)
            self.assertIn("classic_vs_fine_tuned,tfidf_logreg,accuracy", content)
            self.assertIn("loss_by_epoch", content)
