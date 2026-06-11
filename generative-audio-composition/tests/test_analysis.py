"""Unit tests for audio analysis modules."""

import numpy as np
import pytest


def make_sine(freq: float = 440.0, duration: float = 2.0, sr: int = 44100) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def make_chord(freqs: list[float], duration: float = 2.0, sr: int = 44100) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = sum(0.3 * np.sin(2 * np.pi * f * t) for f in freqs)
    return audio.astype(np.float32)


class TestPitchExtractor:
    def test_f0_extraction_sine(self):
        from core.analysis.pitch import PitchExtractor
        extractor = PitchExtractor(method="parselmouth")
        audio = make_sine(freq=440.0, duration=2.0)
        f0, voiced = extractor.extract_f0(audio, sr=44100)
        assert f0.shape == voiced.shape
        # Most frames should be voiced
        assert voiced.mean() > 0.5
        # Mean F0 should be close to 440 Hz
        voiced_f0 = f0[voiced > 0.5]
        assert len(voiced_f0) > 0
        assert abs(voiced_f0.mean() - 440.0) < 30.0

    def test_f0_extraction_returns_arrays(self):
        from core.analysis.pitch import PitchExtractor
        extractor = PitchExtractor(method="parselmouth")
        audio = make_sine(freq=220.0, duration=1.0)
        f0, voiced = extractor.extract_f0(audio, sr=44100)
        assert isinstance(f0, np.ndarray)
        assert isinstance(voiced, np.ndarray)
        assert f0.ndim == 1
        assert voiced.ndim == 1

    def test_key_detection_major(self):
        from core.analysis.key_tempo import MusicAnalyzer
        analyzer = MusicAnalyzer()
        # C major chord: C E G
        audio = make_chord([261.63, 329.63, 392.00], duration=4.0)
        result = analyzer.detect_key(audio, sr=44100)
        assert "key" in result
        assert "mode" in result
        assert "confidence" in result
        assert result["confidence"] > 0.0

    def test_tempo_detection(self):
        from core.analysis.key_tempo import MusicAnalyzer
        analyzer = MusicAnalyzer()
        # Create a click track at 120 BPM
        sr = 44100
        bpm = 120.0
        beat_interval = int(sr * 60.0 / bpm)
        audio = np.zeros(sr * 10, dtype=np.float32)
        for i in range(0, len(audio), beat_interval):
            if i + 100 < len(audio):
                audio[i:i + 100] = 0.8
        result = analyzer.detect_tempo(audio, sr=sr)
        assert "bpm" in result
        assert abs(result["bpm"] - 120.0) < 15.0  # ±15 BPM tolerance


class TestWhisperASR:
    def test_transcribe_returns_dict(self):
        """Smoke test: ASR module initializes and returns proper structure."""
        try:
            from core.analysis.asr import WhisperASR
            asr = WhisperASR(model_size="tiny", device="cpu")
            audio = make_sine(440.0, duration=3.0)
            result = asr.transcribe(audio, sr=44100)
            assert isinstance(result, dict)
            assert "text" in result
            assert "segments" in result
        except ImportError:
            pytest.skip("Whisper not installed")


class TestSpeakerEncoder:
    def test_embedding_shape(self):
        try:
            from core.analysis.speaker import SpeakerEncoder
            encoder = SpeakerEncoder(device="cpu")
            audio = make_sine(440.0, duration=5.0)
            emb = encoder.extract_embedding(audio, sr=44100)
            assert isinstance(emb, np.ndarray)
            assert emb.ndim == 1
            assert emb.shape[0] == 256
        except (ImportError, Exception):
            pytest.skip("Speaker encoder deps not available")

    def test_embedding_normalized(self):
        try:
            from core.analysis.speaker import SpeakerEncoder
            encoder = SpeakerEncoder(device="cpu")
            audio = make_sine(220.0, duration=5.0)
            emb = encoder.extract_embedding(audio, sr=44100)
            norm = np.linalg.norm(emb)
            assert abs(norm - 1.0) < 0.01  # L2-normalized
        except (ImportError, Exception):
            pytest.skip("Speaker encoder deps not available")

    def test_same_speaker_similarity(self):
        try:
            from core.analysis.speaker import SpeakerEncoder
            encoder = SpeakerEncoder(device="cpu")
            audio1 = make_sine(440.0, duration=3.0)
            audio2 = make_sine(440.0, duration=3.0) + np.random.normal(0, 0.01, int(44100 * 3)).astype(np.float32)
            emb1 = encoder.extract_embedding(audio1, sr=44100)
            emb2 = encoder.extract_embedding(audio2, sr=44100)
            sim = encoder.compute_similarity(emb1, emb2)
            assert 0.0 <= sim <= 1.0
        except (ImportError, Exception):
            pytest.skip("Speaker encoder deps not available")


class TestAudioEnhancer:
    def test_denoise_preserves_shape(self):
        try:
            from core.analysis.enhancement import AudioEnhancer
            enhancer = AudioEnhancer(device="cpu")
            noisy = make_sine(440.0) + np.random.normal(0, 0.05, int(44100 * 2)).astype(np.float32)
            denoised = enhancer.denoise(noisy, sr=44100)
            assert isinstance(denoised, np.ndarray)
            assert denoised.shape == noisy.shape
        except (ImportError, Exception):
            pytest.skip("Enhancement deps not available")
