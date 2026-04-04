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
