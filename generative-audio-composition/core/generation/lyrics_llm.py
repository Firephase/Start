"""LLM-based lyrics generation module.

Uses a Llama 3.1 8B model (or a fine-tuned checkpoint) via HuggingFace
Transformers with optional 4-bit quantisation (bitsandbytes / QLoRA).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for the lyrics-completion task
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert songwriter and lyricist. Your task is to generate complete,
structured song lyrics based on partial input, style hints, and a requested
structure.

Rules:
- Always label every section with a marker in square brackets, e.g. [Verse 1],
  [Pre-Chorus], [Chorus], [Bridge], [Outro].
- Write in a consistent voice, mood, and key that matches the style hints.
- Ensure choruses are memorable and repeated where requested.
- Keep verses narrative; keep choruses emotional and hooky.
- Do NOT include any commentary, explanations, or stage directions outside of
  section markers.
- Output ONLY the lyrics.
"""

# Default generation parameters
_DEFAULT_MAX_NEW_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.85
_DEFAULT_TOP_P = 0.92
_DEFAULT_REPETITION_PENALTY = 1.15


class LyricsGenerator:
    """Generate complete structured lyrics using a Llama 3.1-style causal LM.

    Parameters
    ----------
    model_name_or_path:
        HuggingFace model ID or local path to the (fine-tuned) checkpoint.
    device:
        ``'cuda'``, ``'cpu'``, or a specific CUDA device string like
        ``'cuda:0'``.
    load_in_4bit:
        If ``True`` and bitsandbytes is available, load the model in 4-bit
        quantisation (QLoRA-compatible).
    """

    def __init__(
        self,
        model_name_or_path: str = "meta-llama/Meta-Llama-3.1-8B-Instruct",
        device: str = "cuda",
        load_in_4bit: bool = True,
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.device = device
        self.load_in_4bit = load_in_4bit

        self.model = None
        self.tokenizer = None

        self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load the tokenizer and model, with optional 4-bit quantisation."""
        try:
            from transformers import (
                AutoModelForCausalLM,
                AutoTokenizer,
                BitsAndBytesConfig,
            )
            import torch
        except ImportError as exc:
            raise ImportError(
                "The 'transformers' and 'torch' packages are required. "
                "Install them with: pip install transformers torch"
            ) from exc

        logger.info("Loading tokenizer from %s", self.model_name_or_path)
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name_or_path,
            use_fast=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        quantization_config = None
        if self.load_in_4bit:
            try:
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
                logger.info("4-bit quantisation enabled via bitsandbytes")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not configure 4-bit quantisation (%s). "
                    "Falling back to full precision.",
                    exc,
                )

        logger.info("Loading model from %s", self.model_name_or_path)
        model_kwargs: dict = {
            "device_map": "auto" if "cuda" in self.device else self.device,
            "trust_remote_code": True,
        }
        if quantization_config is not None:
            model_kwargs["quantization_config"] = quantization_config
        else:
            model_kwargs["torch_dtype"] = torch.float16 if "cuda" in self.device else torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name_or_path,
            **model_kwargs,
        )
        self.model.eval()
        logger.info("Model loaded successfully")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete_lyrics(
        self,
        partial_lyrics: str,
        style_hints: dict,
        structure: list[str],
        target_sections: int = 8,
    ) -> str:
        """Generate a complete song from partial lyrics and style hints.

        Parameters
        ----------
        partial_lyrics:
            Transcribed or user-provided lyric fragments (may be empty).
        style_hints:
            Dictionary with optional keys: ``genre``, ``mood``, ``key``,
            ``tempo``, ``artist_reference``.
        structure:
            Ordered list of section names, e.g.
            ``['verse', 'chorus', 'verse', 'chorus', 'bridge', 'chorus']``.
        target_sections:
            Fallback number of sections if *structure* is not provided.

        Returns
        -------
        str
            Structured lyrics string with ``[Section]`` markers.
        """
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model is not loaded. Call _load_model() first.")

        if not structure:
            structure = (
                ["verse", "chorus"] * (target_sections // 2)
                if target_sections >= 2
                else ["verse", "chorus"]
            )

        prompt = self._build_prompt(partial_lyrics, style_hints, structure)

        try:
            import torch

            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            with torch.no_grad():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=_DEFAULT_MAX_NEW_TOKENS,
                    temperature=_DEFAULT_TEMPERATURE,
                    top_p=_DEFAULT_TOP_P,
                    repetition_penalty=_DEFAULT_REPETITION_PENALTY,
                    do_sample=True,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )

            # Decode only the newly generated tokens
            input_length = inputs["input_ids"].shape[1]
            generated_ids = output_ids[:, input_length:]
            raw_output = self.tokenizer.decode(
                generated_ids[0], skip_special_tokens=True
            )
        except Exception as exc:
            logger.error("Generation failed: %s", exc)
            raise

        return self._parse_output(raw_output)

    def estimate_style(
        self, transcribed_text: str, genre_hint: Optional[str] = None
    ) -> dict:
        """Infer style attributes from lyric content using simple heuristics.

        A lightweight, model-free estimator based on keyword matching.  For
        production use, replace with an embedding-based classifier.

        Parameters
        ----------
        transcribed_text:
            Raw transcribed or user-written text to analyse.
        genre_hint:
            Optional externally supplied genre that takes priority.

        Returns
        -------
        dict
            Keys: ``genre``, ``mood``, ``key``, ``tempo``.
        """
        text_lower = transcribed_text.lower()

        # ----- Genre estimation -------------------------------------------
        genre_keywords: dict[str, list[str]] = {
            "pop": ["love", "heart", "feel", "tonight", "dance", "baby"],
            "rock": ["fire", "rage", "storm", "break", "scream", "fight"],
            "hip-hop": ["flow", "grind", "hustle", "streets", "real", "game"],
            "r&b": ["smooth", "soul", "body", "touch", "vibe", "night"],
            "country": ["road", "home", "dirt", "truck", "whiskey", "stars"],
            "folk": ["river", "wind", "mountain", "tree", "wander", "dream"],
            "electronic": ["pulse", "wave", "neon", "beat", "synth", "drop"],
        }
        genre = genre_hint or "pop"
        if not genre_hint:
            best_genre = "pop"
            best_score = -1
            for g, keywords in genre_keywords.items():
                score = sum(text_lower.count(kw) for kw in keywords)
                if score > best_score:
                    best_score = score
                    best_genre = g
            genre = best_genre

        # ----- Mood estimation --------------------------------------------
        positive_words = {"happy", "joy", "love", "bright", "shine", "smile", "hope"}
        negative_words = {"sad", "pain", "hurt", "cry", "dark", "lost", "alone"}
        pos = sum(1 for w in text_lower.split() if w.strip(".,!?") in positive_words)
        neg = sum(1 for w in text_lower.split() if w.strip(".,!?") in negative_words)
        if pos > neg:
            mood = "uplifting"
        elif neg > pos:
            mood = "melancholic"
        else:
            mood = "neutral"

        # ----- Tempo estimation -------------------------------------------
        # More exclamation marks / short sentences → faster feel
        exclamations = text_lower.count("!")
        sentences = max(1, text_lower.count(".") + text_lower.count("!") + text_lower.count("?"))
        avg_sentence_words = len(text_lower.split()) / sentences
        if exclamations > 3 or avg_sentence_words < 6:
            tempo = "fast"
        elif avg_sentence_words > 12:
            tempo = "slow"
        else:
            tempo = "medium"

        return {
            "genre": genre,
            "mood": mood,
            "key": "C major",  # Default; real inference requires audio analysis
            "tempo": tempo,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        partial_lyrics: str,
        style_hints: dict,
        structure: list[str],
    ) -> str:
        """Build the system + user prompt for the lyrics-completion task.

        Parameters
        ----------
        partial_lyrics:
            Existing lyric fragments (may be empty string).
        style_hints:
            Style dictionary (see :meth:`complete_lyrics`).
        structure:
            Ordered section name list.

        Returns
        -------
        str
            Formatted prompt string ready for tokenisation.
        """
        genre = style_hints.get("genre", "pop")
        mood = style_hints.get("mood", "uplifting")
        key = style_hints.get("key", "C major")
        tempo = style_hints.get("tempo", "medium")
        artist_ref = style_hints.get("artist_reference", "")

        structure_str = " → ".join(s.title() for s in structure)

        style_block = (
            f"Genre: {genre}\n"
            f"Mood: {mood}\n"
            f"Key: {key}\n"
            f"Tempo: {tempo}\n"
        )
        if artist_ref:
            style_block += f"Artist reference: {artist_ref}\n"

        user_lines = [
            "Complete the following song with structured lyrics.",
            "",
            f"## Style\n{style_block}",
            f"## Structure\n{structure_str}",
        ]

        if partial_lyrics and partial_lyrics.strip():
            user_lines += [
                "",
                "## Partial Lyrics (incorporate or extend these ideas)",
                partial_lyrics.strip(),
            ]

        user_lines += [
            "",
            "## Instructions",
            "- Write each section preceded by its label in square brackets, e.g. [Verse 1].",
            "- Follow the structure exactly.",
            "- Output ONLY the lyrics, no other text.",
            "",
            "## Output",
        ]

        user_message = "\n".join(user_lines)

        # Format as Llama 3.1 chat template if supported; fall back to plain
        if self.tokenizer is not None and hasattr(self.tokenizer, "apply_chat_template"):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]
            try:
                return self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                )
            except Exception:  # noqa: BLE001
                pass

        # Fallback: simple concatenation
        return (
            f"<|system|>\n{SYSTEM_PROMPT}\n<|end|>\n"
            f"<|user|>\n{user_message}\n<|end|>\n"
            f"<|assistant|>\n"
        )

    def _parse_output(self, raw_output: str) -> str:
        """Clean and validate the raw model output.

        - Strips leading/trailing whitespace.
        - Removes any text before the first ``[`` section marker.
        - Normalises section headers to Title Case inside brackets.
        - Collapses more than two consecutive blank lines.

        Parameters
        ----------
        raw_output:
            Raw decoded string from the model.

        Returns
        -------
        str
            Cleaned lyrics string.
        """
        text = raw_output.strip()

        # Remove text before the first section marker
        first_bracket = text.find("[")
        if first_bracket > 0:
            text = text[first_bracket:]

        # Normalise section headers: [verse 1] → [Verse 1]
        def _title_marker(m: re.Match) -> str:
            inner = m.group(1).strip()
            return f"[{inner.title()}]"

        text = re.sub(r"\[([^\]]+)\]", _title_marker, text)

        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove any trailing model-generated commentary after a final section
        # (heuristic: stop at lines starting with "Note:", "---", "###")
        lines = text.splitlines()
        clean_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^(Note:|---|###|Output:|Instructions:)", stripped, re.IGNORECASE):
                break
            clean_lines.append(line)

        return "\n".join(clean_lines).strip()
