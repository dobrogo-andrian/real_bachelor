import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from model_fine_tuning import prepare_and_balance_data


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_module_from_path(module_name: str, relative_path: str):
    module_path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PrepareAndBalanceExportsTests(unittest.TestCase):
    def test_find_data_files_ignores_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Sp1786-multiclass-sentiment-analysis-dataset" / "hf_saved_dataset").mkdir(parents=True)
            (root / "Sp1786-multiclass-sentiment-analysis-dataset" / "hf_saved_dataset" / "full_dataset.csv").write_text(
                "text,label\nhello,1\n",
                encoding="utf-8",
            )
            (root / "balanced_sentiment_dataset").mkdir(parents=True)
            (root / "balanced_sentiment_dataset" / "balanced_dataset.csv").write_text("text,label\nskip,0\n", encoding="utf-8")
            (root / "sentiment_lora_adapters").mkdir(parents=True)
            (root / "sentiment_lora_adapters" / "adapter_config.json").write_text("{}", encoding="utf-8")
            (root / "artifacts" / "evaluation").mkdir(parents=True)
            (root / "artifacts" / "evaluation" / "model_comparison.json").write_text("{}", encoding="utf-8")

            discovered = prepare_and_balance_data.find_data_files(root)

            self.assertEqual(
                discovered,
                [root / "Sp1786-multiclass-sentiment-analysis-dataset" / "hf_saved_dataset" / "full_dataset.csv"],
            )

    def test_default_export_writes_only_csv(self):
        frame = pd.DataFrame({"text": ["alpha", "beta"], "label": [0, 2]})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prepare_and_balance_data.save_balanced_dataset_exports(frame, output_dir, save_hf_dataset=False)

            self.assertTrue((output_dir / "balanced_dataset.csv").exists())
            self.assertTrue((output_dir / "dataset_manifest.json").exists())
            self.assertFalse((output_dir / "dataset_info.json").exists())
            self.assertFalse((output_dir / "state.json").exists())
            self.assertFalse((output_dir / "data-00000-of-00001.arrow").exists())

    def test_optional_hf_export_calls_save_to_disk(self):
        frame = pd.DataFrame({"text": ["alpha"], "label": [1]})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            fake_dataset = type("FakeDataset", (), {"save_to_disk": lambda self, path: Path(path, "state.json").write_text("{}", encoding="utf-8")})()

            with patch("datasets.Dataset.from_pandas", return_value=fake_dataset) as from_pandas:
                prepare_and_balance_data.save_balanced_dataset_exports(frame, output_dir, save_hf_dataset=True)

            from_pandas.assert_called_once()
            self.assertTrue((output_dir / "balanced_dataset.csv").exists())
            self.assertTrue((output_dir / "dataset_manifest.json").exists())
            self.assertTrue((output_dir / "state.json").exists())

    def test_manifest_includes_source_provenance_when_provided(self):
        frame = pd.DataFrame({"text": ["alpha", "beta", "gamma"], "label": [0, 1, 2]})
        manifest = {
            "dataset_name": "balanced_sentiment_dataset",
            "source_files": [
                {
                    "file_name": "source.csv",
                    "file_path": "model_fine_tuning/source.csv",
                    "status": "processed",
                    "raw_row_count": 10,
                    "standardized_row_count": 6,
                    "dropped_row_count": 4,
                    "text_column": "text",
                    "label_source": "label",
                    "class_distribution": {"negative": 2, "neutral": 2, "positive": 2},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prepare_and_balance_data.save_balanced_dataset_exports(
                frame,
                output_dir,
                save_hf_dataset=False,
                manifest=manifest,
            )

            payload = json.loads((output_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["dataset_name"], "balanced_sentiment_dataset")
            self.assertEqual(len(payload["source_files"]), 1)
            self.assertEqual(payload["source_files"][0]["file_name"], "source.csv")


class DownloadDatasetExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sp_module = load_module_from_path(
            "sp1786_download_dataset",
            "model_fine_tuning/Sp1786-multiclass-sentiment-analysis-dataset/download_dataset.py",
        )
        cls.ukr_module = load_module_from_path(
            "ukr_download_dataset",
            "model_fine_tuning/ukr-detect-ukr-emotions-binary/download_dataset.py",
        )

    def test_sp1786_default_export_skips_hf_artifacts(self):
        class FakeDataset:
            def __init__(self):
                self.saved = False

            def to_csv(self, path, index=False):
                Path(path).write_text("text,label\nhello,1\n", encoding="utf-8")

            def save_to_disk(self, path):
                self.saved = True
                Path(path, "state.json").write_text("{}", encoding="utf-8")

        dataset = FakeDataset()
        with tempfile.TemporaryDirectory() as temp_dir:
            self.sp_module.save_unified_dataset_exports(dataset, temp_dir, save_hf_dataset=False)
            self.assertTrue((Path(temp_dir) / "full_dataset.csv").exists())
            self.assertFalse(dataset.saved)
            self.assertFalse((Path(temp_dir) / "state.json").exists())

    def test_ukr_default_export_skips_hf_artifacts(self):
        frame = pd.DataFrame({"text": ["hello"], "label": [2], "sentiment_name": ["positive"]})

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("datasets.Dataset.from_pandas") as from_pandas:
                self.ukr_module.save_balanced_dataset_exports(frame, temp_dir, save_hf_dataset=False)

            from_pandas.assert_not_called()
            self.assertTrue((Path(temp_dir) / "full_balanced_dataset.csv").exists())
            self.assertFalse((Path(temp_dir) / "state.json").exists())
