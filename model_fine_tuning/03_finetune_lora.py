"""
Stage 3:
Load the processed dataset from disk and fine-tune the base model with LoRA adapters.

Saves:
    - LoRA adapters only
    - tokenizer
"""

from __future__ import annotations

import os

from datasets import load_from_disk
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

from common import LABEL_NAMES, MODEL_NAME, bitsandbytes_available, compute_metrics, parse_config


def build_model():
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=3,
        id2label=LABEL_NAMES,
        label2id={value: key for key, value in LABEL_NAMES.items()},
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=16,
        lora_alpha=32,
        lora_dropout=0.1,
        target_modules=["query", "value"],
        modules_to_save=["classifier"],
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.enable_input_require_grads()
    model.print_trainable_parameters()
    return model


def build_training_args(config):
    optim_name = "paged_adamw_8bit" if bitsandbytes_available() else "adamw_torch"
    print(f"[training] optimizer = {optim_name}")

    return TrainingArguments(
        output_dir=config.adapter_output_dir,
        learning_rate=config.learning_rate,
        per_device_train_batch_size=config.per_device_train_batch_size,
        per_device_eval_batch_size=config.per_device_eval_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        num_train_epochs=config.num_train_epochs,
        weight_decay=config.weight_decay,
        warmup_ratio=config.warmup_ratio,
        evaluation_strategy=config.eval_strategy,
        save_strategy=config.save_strategy,
        eval_steps=config.eval_steps,
        save_steps=config.save_steps,
        logging_steps=config.logging_steps,
        fp16=True,
        gradient_checkpointing=True,
        optim=optim_name,
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        report_to="none",
        seed=config.seed,
        save_total_limit=2,
    )


def main() -> None:
    config = parse_config("Stage 3: LoRA fine-tuning")

    print(f"[load] reading processed dataset from: {config.processed_output_dir}")
    tokenized_datasets = load_from_disk(config.processed_output_dir)

    print("[setup] loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(config.processed_output_dir)

    print("[setup] building model...")
    model = build_model()

    training_args = build_training_args(config)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer, pad_to_multiple_of=8)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets["validation"],
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    print("[train] starting training...")
    trainer.train()

    print("[save] saving LoRA adapters only...")
    os.makedirs(config.adapter_output_dir, exist_ok=True)
    model.save_pretrained(config.adapter_output_dir)
    tokenizer.save_pretrained(config.adapter_output_dir)
    print(f"[done] adapters saved to: {config.adapter_output_dir}")


if __name__ == "__main__":
    main()
