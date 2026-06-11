"""
MusicGen LoRA fine-tuning wrapper.
Applies LoRA adapters to facebook/musicgen-large using PEFT.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
from peft import LoraConfig, get_peft_model, TaskType, PeftModel

logger = logging.getLogger(__name__)


class MusicGenLoRAFinetuner:
    """Wraps MusicGen-large with LoRA for efficient fine-tuning."""

    def __init__(
        self,
        base_model_id: str = "facebook/musicgen-large",
        lora_r: int = 16,
        lora_alpha: int = 32,
        lora_dropout: float = 0.05,
        device: str = "cuda",
    ):
        self.device = device
        self.base_model_id = base_model_id
        self.lora_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            bias="none",
            target_modules=["q_proj", "v_proj", "k_proj", "out_proj"],
        )

    def build_model(self):
        """Load MusicGen and apply LoRA adapters."""
        try:
            from audiocraft.models import MusicGen
        except ImportError as e:
            raise ImportError("audiocraft is required: pip install audiocraft") from e

        logger.info("Loading base model: %s", self.base_model_id)
        model = MusicGen.get_pretrained(self.base_model_id)
        model = model.to(self.device)

        # Apply LoRA to the LM (transformer) component
        lm = model.lm
        lm = get_peft_model(lm, self.lora_config)
        lm.print_trainable_parameters()
        model.lm = lm

        return model

    def save_adapter(self, model, output_dir: str):
        """Save only the LoRA adapter weights."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        model.lm.save_pretrained(output_dir)
        logger.info("LoRA adapter saved to %s", output_dir)

    def load_adapter(self, base_model, adapter_path: str):
        """Load LoRA adapter into base model."""
        base_model.lm = PeftModel.from_pretrained(base_model.lm, adapter_path)
        logger.info("LoRA adapter loaded from %s", adapter_path)
        return base_model

    def get_trainable_params(self, model) -> int:
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
