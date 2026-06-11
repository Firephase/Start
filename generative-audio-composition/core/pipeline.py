"""
End-to-end generation pipeline orchestrator.

Input:  list of audio file paths (amateur singing fragments)
Output: numpy array (stereo 44100Hz) + metadata dict

Pipeline stages:
  1. Enhancement   – denoise + separate vocals
  2. Analysis      – ASR (lyrics) + pitch/key/tempo + speaker embedding
  3. Lyrics LLM    – complete & structure lyrics
  4. Instrumental  – generate arrangement via MusicGen
  5. SVS           – synthesize vocals in user's voice (DiffSinger)
  6. Mixing        – stem mix + mastering
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


@dataclass
class GenerationRequest:
    audio_paths: list[str]
    target_duration: float = 180.0          # seconds
    structure: Optional[list[str]] = None   # ['verse','chorus',...] or None=auto
    genre_hint: Optional[str] = None
    output_format: str = "wav"              # 'wav' or 'mp3'
    fast_sampling: bool = True              # use DDIM for SVS


@dataclass
class GenerationResult:
    audio: np.ndarray                       # stereo float32, 44100Hz
    sample_rate: int = 44100
    duration: float = 0.0
    lyrics: str = ""
    key: str = ""
    bpm: float = 0.0
    genre: str = ""
    structure: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AudioPipeline:
    """Orchestrates the full generation pipeline."""

    def __init__(self, config: dict):
        self.config = config
        self.device = config.get("device", "cuda")
        self._models: dict = {}

    # ── Lazy model loading ─────────────────────────────────────────────────────

    @property
    def enhancer(self):
        if "enhancer" not in self._models:
            from core.analysis.enhancement import AudioEnhancer
            self._models["enhancer"] = AudioEnhancer(device=self.device)
        return self._models["enhancer"]

    @property
    def asr(self):
        if "asr" not in self._models:
            from core.analysis.asr import WhisperASR
            self._models["asr"] = WhisperASR(
                model_size=self.config.get("whisper_size", "large-v3"),
                device=self.device,
            )
        return self._models["asr"]

    @property
    def pitch_extractor(self):
        if "pitch" not in self._models:
            from core.analysis.pitch import PitchExtractor
            self._models["pitch"] = PitchExtractor(device=self.device)
        return self._models["pitch"]

    @property
    def speaker_encoder(self):
        if "speaker" not in self._models:
            from core.analysis.speaker import SpeakerEncoder
            self._models["speaker"] = SpeakerEncoder(
                model_path=self.config.get("speaker_encoder_path"),
                device=self.device,
            )
        return self._models["speaker"]

    @property
    def music_analyzer(self):
        if "music_analyzer" not in self._models:
            from core.analysis.key_tempo import MusicAnalyzer
            self._models["music_analyzer"] = MusicAnalyzer()
        return self._models["music_analyzer"]

    @property
    def lyrics_llm(self):
        if "lyrics_llm" not in self._models:
            from core.generation.lyrics_llm import LyricsGenerator
            self._models["lyrics_llm"] = LyricsGenerator(
                model_name_or_path=self.config.get("lyrics_model_path", "meta-llama/Meta-Llama-3.1-8B-Instruct"),
                device=self.device,
            )
        return self._models["lyrics_llm"]

    @property
    def structure_planner(self):
        if "structure" not in self._models:
            from core.generation.structure import SongStructurePlanner
            self._models["structure"] = SongStructurePlanner()
        return self._models["structure"]

    @property
    def instrumental_generator(self):
        if "instrumental" not in self._models:
            from core.generation.music_gen import InstrumentalGenerator
            self._models["instrumental"] = InstrumentalGenerator(
                model_path=self.config.get("musicgen_path", "facebook/musicgen-large"),
                device=self.device,
            )
        return self._models["instrumental"]

    @property
    def svs(self):
        if "svs" not in self._models:
            from core.generation.svs import SingingVoiceSynthesizer
            self._models["svs"] = SingingVoiceSynthesizer(
                model_path=self.config.get("diffsinger_path", ""),
                device=self.device,
            )
        return self._models["svs"]

    @property
    def mixer(self):
        if "mixer" not in self._models:
            from core.mixing.mixer import StemMixer
            self._models["mixer"] = StemMixer(target_sr=44100)
        return self._models["mixer"]

    @property
    def mastering(self):
        if "mastering" not in self._models:
            from core.mixing.mastering import NeuralMastering
            self._models["mastering"] = NeuralMastering(sample_rate=44100)
        return self._models["mastering"]

    # ── Pipeline stages ────────────────────────────────────────────────────────

    def _stage_load_and_enhance(self, audio_paths: list[str]) -> list[dict]:
        """Load audio files, denoise, separate vocals."""
        import torchaudio
        logger.info("Stage 1: Loading and enhancing %d audio files", len(audio_paths))
        fragments = []
        for path in audio_paths:
            audio, sr = sf.read(path, dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)  # to mono for analysis
            enhanced_vocals, _ = self.enhancer.separate_vocals(audio, sr)
            denoised = self.enhancer.denoise(enhanced_vocals, sr)
            fragments.append({"path": path, "audio": denoised, "sr": sr})
        return fragments

    def _stage_analyze(self, fragments: list[dict]) -> dict:
        """Run ASR, pitch, key/tempo, speaker embedding on all fragments."""
        logger.info("Stage 2: Analyzing fragments")
        all_lyrics: list[str] = []
        all_f0: list[np.ndarray] = []
        speaker_segments: list[np.ndarray] = []

        for frag in fragments:
            audio = frag["audio"]
            sr = frag["sr"]

            # ASR
            transcript = self.asr.transcribe(audio, sr)
            if transcript["text"].strip():
                all_lyrics.append(transcript["text"].strip())

            # Pitch extraction
            melody = self.pitch_extractor.extract_melody_contour(audio, sr)
            all_f0.append(melody["f0"])

            # Speaker segments (need 16kHz mono)
            speaker_segments.append(audio)

        # Key + tempo from concatenated audio
        combined = np.concatenate([f["audio"] for f in fragments])
        combined_sr = fragments[0]["sr"]
        music_info = self.music_analyzer.analyze(combined, combined_sr)

        # Speaker embedding: average over all fragments
        speaker_embedding = self.speaker_encoder.extract_embedding_from_segments(
            speaker_segments, combined_sr
        )

        return {
            "partial_lyrics": " ".join(all_lyrics),
            "f0_contours": all_f0,
            "speaker_embedding": speaker_embedding,
            "key": music_info["key"],
            "mode": music_info["mode"],
            "bpm": music_info["bpm"],
            "beat_times": music_info.get("beat_times"),
        }

    def _stage_generate_lyrics(self, analysis: dict, request: GenerationRequest) -> dict:
        """Complete partial lyrics into structured song."""
        logger.info("Stage 3: Generating lyrics")
        style_hints = {
            "key": analysis["key"],
            "bpm": analysis["bpm"],
            "genre": request.genre_hint or "pop",
        }
        structure_spec = request.structure or ["verse", "chorus", "verse", "chorus", "bridge", "chorus"]
        full_lyrics = self.lyrics_llm.complete_lyrics(
            partial_lyrics=analysis["partial_lyrics"],
            style_hints=style_hints,
            structure=structure_spec,
        )
        sections = self.structure_planner.plan_from_lyrics(full_lyrics, request.target_duration)
        return {"full_lyrics": full_lyrics, "sections": sections}

    def _stage_generate_instrumental(self, analysis: dict, lyrics_result: dict, request: GenerationRequest) -> np.ndarray:
        """Generate instrumental arrangement via MusicGen."""
        logger.info("Stage 4: Generating instrumental arrangement")
        # Build melody reference from F0 contours
        combined_f0 = np.concatenate(analysis["f0_contours"])

        # Convert F0 to a simple melody audio signal for MusicGen conditioning
        melody_audio = self._f0_to_sine(combined_f0, sr=44100)

        genre = request.genre_hint or "pop"
        instrumental = self.instrumental_generator.generate_full_arrangement(
            structure=[s.section_type for s in lyrics_result["sections"]],
            key=analysis["key"],
            bpm=analysis["bpm"],
            melody_audio=melody_audio,
            genre=genre,
        )
        return instrumental

    def _stage_synthesize_vocals(self, analysis: dict, lyrics_result: dict, request: GenerationRequest) -> np.ndarray:
        """Synthesize vocals in user's cloned voice via DiffSinger."""
        logger.info("Stage 5: Synthesizing vocals (DiffSinger)")
        vocals = self.svs.synthesize_full_song(
            structure=lyrics_result["sections"],
            speaker_embedding=analysis["speaker_embedding"],
            bpm=analysis["bpm"],
        )
        return vocals

    def _stage_mix_and_master(self, vocals: np.ndarray, instrumental: np.ndarray) -> np.ndarray:
        """Mix stems and apply mastering chain."""
        logger.info("Stage 6: Mixing and mastering")
        vocals = self.mixer.create_vocal_chain(vocals, sr=44100)
        instrumental = self.mixer.create_instrumental_chain(instrumental, sr=32000)
        mixed = self.mixer.mix(vocals, instrumental, instrumental_sr=32000)
        mastered = self.mastering.master(mixed)
        return mastered

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Run the full pipeline end-to-end."""
        t0 = time.monotonic()

        fragments = self._stage_load_and_enhance(request.audio_paths)
        analysis = self._stage_analyze(fragments)
        lyrics_result = self._stage_generate_lyrics(analysis, request)
        instrumental = self._stage_generate_instrumental(analysis, lyrics_result, request)
        vocals = self._stage_synthesize_vocals(analysis, lyrics_result, request)
        final_audio = self._stage_mix_and_master(vocals, instrumental)

        elapsed = time.monotonic() - t0
        logger.info("Pipeline completed in %.1f seconds", elapsed)

        return GenerationResult(
            audio=final_audio,
            sample_rate=44100,
            duration=final_audio.shape[-1] / 44100,
            lyrics=lyrics_result["full_lyrics"],
            key=analysis["key"],
            bpm=analysis["bpm"],
            genre=request.genre_hint or "auto",
            structure=[s.section_type for s in lyrics_result["sections"]],
            metadata={
                "generation_time_seconds": elapsed,
                "speaker_embedding_norm": float(np.linalg.norm(analysis["speaker_embedding"])),
                "num_input_fragments": len(request.audio_paths),
            },
        )

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def _f0_to_sine(f0: np.ndarray, sr: int = 44100, hop_length: int = 512) -> np.ndarray:
        """Convert F0 contour to a sine-wave melody signal for MusicGen conditioning."""
        n_samples = len(f0) * hop_length
        audio = np.zeros(n_samples, dtype=np.float32)
        phase = 0.0
        for i, freq in enumerate(f0):
            if freq > 0:
                start = i * hop_length
                end = min(start + hop_length, n_samples)
                t = np.arange(end - start) / sr
                chunk = 0.5 * np.sin(2 * np.pi * freq * t + phase)
                audio[start:end] = chunk
                phase += 2 * np.pi * freq * hop_length / sr
        return audio
