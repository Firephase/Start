#!/usr/bin/env python3
"""
Fine-tune Llama 3.1 8B on lyrics dataset using QLoRA.
Usage: python training/train_lyrics_llm.py --config configs/model/lyrics_llm.yaml
"""

import argparse
import json
import logging
import os
from pathlib import Path

import torch
from datasets import Dataset, load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    TrainingArguments,
    Trainer,
)
import wandb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a professional songwriter. Complete the given partial lyrics into "
    "a full song with proper structure. Use [Verse 1], [Verse 2], [Chorus], [Bridge] "
    "section markers. Keep the original style, rhyme scheme, and themes."
)


def format_example(example: dict) -> dict:
    """Format a lyrics example into a chat-style prompt."""
    partial = example.get("partial_lyrics", "")
    full = example.get("full_lyrics", "")
    genre = example.get("genre", "pop")
    key = example.get("key", "C major")
    bpm = example.get("bpm", 120)

    user_msg = (
        f"Genre: {genre}, Key: {key}, Tempo: {bpm} BPM\n\n"
        f"Partial lyrics (transcribed from recording):\n{partial}\n\n"
        f"Complete this into a full structured song:"
    )

    text = (
        f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
        f"{SYSTEM_PROMPT}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n"
        f"{user_msg}<|eot_id|>"
        f"<|start_header_id|>assistant<|end_header_id|>\n"
        f"{full}<|eot_id|>"
    )
    return {"text": text}


def load_lyrics_dataset(data_path: str, val_split: float = 0.05) -> tuple:
    """Load and prepare lyrics dataset."""
    if data_path.endswith(".json") or data_path.endswith(".jsonl"):
        with open(data_path) as f:
            if data_path.endswith(".jsonl"):
                records = [json.loads(l) for l in f]
            else:
                records = json.load(f)
        dataset = Dataset.from_list(records)
    else:
        # Try HuggingFace dataset
        dataset = load_dataset(data_path, split="train")

    dataset = dataset.map(format_example, remove_columns=dataset.column_names)
    splits = dataset.train_test_split(test_size=val_split, seed=42)
    return splits["train"], splits["test"]


def build_model_and_tokenizer(model_name: str, lora_config_dict: dict):
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )
    model = prepare_model_for_kbit_training(model)

    lora_cfg = LoraConfig(
        r=lora_config_dict.get("lora_r", 64),
        lora_alpha=lora_config_dict.get("lora_alpha", 128),
        target_modules=lora_config_dict.get(
            "target_modules",
            ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        ),
        lora_dropout=lora_config_dict.get("lora_dropout", 0.05),
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    return model, tokenizer


def tokenize_dataset(dataset, tokenizer, max_length: int = 2048):
    def tokenize(example):
        result = tokenizer(
            example["text"],
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        result["labels"] = result["input_ids"].copy()
        return result

    return dataset.map(tokenize, batched=True, remove_columns=["text"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/model/lyrics_llm.yaml")
    parser.add_argument("--data_path", required=True, help="Path to lyrics dataset JSON/JSONL")
    parser.add_argument("--output_dir", default="outputs/lyrics_llm")
    parser.add_argument("--num_train_epochs", type=int, default=3)
    parser.add_argument("--per_device_train_batch_size", type=int, default=4)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--run_name", default="lyrics-llm-finetune")
    args = parser.parse_args()

    import yaml
    with open(args.config) as f:
        config = yaml.safe_load(f)

    model_cfg = config["model"]
    base_model = model_cfg["base_model"]
    lora_cfg = model_cfg["finetune"]

    wandb.init(project="generative-audio-composition", name=args.run_name)

    logger.info("Loading dataset from %s", args.data_path)
    train_ds, val_ds = load_lyrics_dataset(args.data_path)
    logger.info("Train: %d, Val: %d", len(train_ds), len(val_ds))

    logger.info("Loading model: %s", base_model)
    model, tokenizer = build_model_and_tokenizer(base_model, lora_cfg)

    train_ds = tokenize_dataset(train_ds, tokenizer)
    val_ds = tokenize_dataset(val_ds, tokenizer)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=500,
        save_total_limit=3,
        load_best_model_at_end=True,
        bf16=True,
        tf32=True,
        optim="paged_adamw_32bit",
        dataloader_num_workers=4,
        report_to="wandb",
        run_name=args.run_name,
        gradient_checkpointing=True,
        group_by_length=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        data_collator=DataCollatorForSeq2Seq(tokenizer, pad_to_multiple_of=8),
    )

    logger.info("Starting training")
    trainer.train()

    output_path = Path(args.output_dir) / "final"
    model.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))
    logger.info("Model saved to %s", output_path)

    wandb.finish()


if __name__ == "__main__":
    main()
