import importlib.util
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
    def test_default_export_writes_only_csv(self):
        frame = pd.DataFrame({"text": ["alpha", "beta"], "label": [0, 2]})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prepare_and_balance_data.save_balanced_dataset_exports(frame, output_dir, save_hf_dataset=False)

            self.assertTrue((output_dir / "balanced_dataset.csv").exists())
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
            self.assertTrue((output_dir / "state.json").exists())


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
