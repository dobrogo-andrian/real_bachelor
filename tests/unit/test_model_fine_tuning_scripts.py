import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from model_fine_tuning import common, train_lora_sentiment


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_module_from_path(module_name: str, relative_path: str):
    module_path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CommonModuleTests(unittest.TestCase):
    def test_pick_first_existing_column_is_case_insensitive(self):
        column = common.pick_first_existing_column(["Text", "Sentiment"], ["text", "comment"], "dataset")
        self.assertEqual(column, "Text")


class TrainLoraSentimentTests(unittest.TestCase):
    def build_config(self) -> train_lora_sentiment.ScriptConfig:
        return train_lora_sentiment.ScriptConfig(
            csv_path=Path("dataset.csv"),
            output_dir=Path("output"),
            model_name="model",
            max_length=128,
            seed=7,
            num_train_epochs=2.0,
            learning_rate=1e-4,
            weight_decay=0.02,
            per_device_train_batch_size=4,
            per_device_eval_batch_size=8,
            gradient_accumulation_steps=3,
            eval_strategy="steps",
            save_strategy="steps",
            logging_steps=11,
            eval_steps=None,
            save_steps=None,
            warmup_ratio=0.15,
        )

    def test_resolve_precision_config_cpu(self):
        with patch("torch.cuda.is_available", return_value=False):
            precision = train_lora_sentiment.resolve_precision_config()

        self.assertFalse(precision.fp16)
        self.assertFalse(precision.bf16)
        self.assertIsNone(precision.pad_to_multiple_of)
        self.assertEqual(precision.accelerator_name, "cpu")

    def test_resolve_precision_config_bf16(self):
        with patch("torch.cuda.is_available", return_value=True), patch("torch.cuda.is_bf16_supported", return_value=True):
            precision = train_lora_sentiment.resolve_precision_config()

        self.assertFalse(precision.fp16)
        self.assertTrue(precision.bf16)
        self.assertEqual(precision.pad_to_multiple_of, 8)

    def test_build_training_arguments_uses_runtime_config(self):
        config = self.build_config()
        precision = train_lora_sentiment.PrecisionConfig(fp16=False, bf16=True, pad_to_multiple_of=8, accelerator_name="cuda-bf16")

        training_args = train_lora_sentiment.build_training_arguments(config, precision, train_dataset_size=120)

        self.assertEqual(training_args.eval_strategy.value, "steps")
        self.assertEqual(training_args.save_strategy.value, "steps")
        self.assertEqual(training_args.eval_steps, 11)
        self.assertEqual(training_args.save_steps, 11)
        self.assertEqual(training_args.warmup_steps, 3)
        self.assertFalse(training_args.fp16)
        self.assertTrue(training_args.bf16)


class SymbolsGenerationTests(unittest.TestCase):
    def test_import_has_no_file_side_effects(self):
        with patch("pandas.DataFrame.to_csv") as to_csv:
            module = load_module_from_path("symbols_generation_module", "model_fine_tuning/symbols/generation.py")

        to_csv.assert_not_called()
        self.assertTrue(hasattr(module, "build_synthetic_dataset"))

    def test_build_synthetic_dataset_returns_non_empty_frame(self):
        module = load_module_from_path("symbols_generation_dataset_module", "model_fine_tuning/symbols/generation.py")
        frame = module.build_synthetic_dataset(seed=42)

        self.assertFalse(frame.empty)
        self.assertEqual(set(frame.columns), {"text", "label"})
        self.assertTrue(frame["text"].str.strip().ne("").all())
