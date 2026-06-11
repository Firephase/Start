"""Unit tests for generation modules."""

import numpy as np
import pytest


class TestSongStructurePlanner:
    def test_plan_from_lyrics_standard(self):
        from core.generation.structure import SongStructurePlanner
        planner = SongStructurePlanner()
        lyrics = (
            "[Verse 1]\nSome verse lyrics here\nMore lines\n\n"
            "[Chorus]\nChorus lyrics here\n\n"
            "[Verse 2]\nSecond verse lyrics\n\n"
            "[Chorus]\nChorus again\n"
        )
        sections = planner.plan_from_lyrics(lyrics, target_duration=180.0)
        assert len(sections) > 0
        types = [s.section_type for s in sections]
        assert "verse" in types
        assert "chorus" in types

    def test_plan_from_spec(self):
        from core.generation.structure import SongStructurePlanner
        planner = SongStructurePlanner()
        spec = ["verse", "chorus", "verse", "chorus", "bridge", "chorus"]
        lyrics_by_section = {
            "verse": ["Line one\nLine two", "Line three\nLine four"],
            "chorus": ["Chorus line one\nChorus line two"] * 3,
            "bridge": ["Bridge line"],
        }
        sections = planner.plan_from_spec(spec, lyrics_by_section, target_duration=180.0)
        assert len(sections) == 6
        assert sections[0].section_type == "verse"
        assert sections[1].section_type == "chorus"

    def test_lyrics_to_sections_parses_markers(self):
        from core.generation.structure import SongStructurePlanner
        planner = SongStructurePlanner()
        raw = "[Verse 1]\nHello world\n\n[Chorus]\nFly away\n\n[Bridge]\nIn between"
        sections_dict = planner.lyrics_to_sections(raw)
        assert "verse" in sections_dict
        assert "chorus" in sections_dict
        assert "bridge" in sections_dict

    def test_estimate_section_duration(self):
        from core.generation.structure import SongStructurePlanner
        planner = SongStructurePlanner()
        lyrics = "Hello world how are you today\nAnother line of singing here"
        dur = planner.estimate_section_duration(lyrics, bpm=120.0)
        assert dur > 0.0
        assert dur < 120.0  # sanity check

    def test_repeat_to_fill(self):
        from core.generation.structure import SongStructurePlanner, SongSection
        planner = SongStructurePlanner()
        sections = [
            SongSection("verse", "Some lyrics", 0.0, 20.0),
            SongSection("chorus", "Chorus lyrics", 20.0, 35.0),
        ]
        filled = planner.repeat_to_fill(sections, target_duration=120.0)
        total = sum(s.end_time - s.start_time for s in filled)
        assert total >= 100.0  # should expand to fill target


class TestMixingChain:
    def test_stem_mixer_output_shape(self):
        from core.mixing.mixer import StemMixer
        mixer = StemMixer(target_sr=44100)
        vocals = np.random.randn(44100 * 3).astype(np.float32) * 0.3
        instrumental = np.random.randn(2, 32000 * 3).astype(np.float32) * 0.3
        result = mixer.mix(vocals, instrumental, instrumental_sr=32000)
        assert result.ndim == 2
        assert result.shape[0] == 2  # stereo

    def test_stem_mixer_no_clipping(self):
        from core.mixing.mixer import StemMixer
        mixer = StemMixer(target_sr=44100)
        vocals = np.ones(44100 * 3, dtype=np.float32) * 0.5
        instrumental = np.ones((2, 32000 * 3), dtype=np.float32) * 0.5
        result = mixer.mix(vocals, instrumental, instrumental_sr=32000)
        assert np.abs(result).max() <= 1.0

    def test_mastering_lufs_normalization(self):
        from core.mixing.mastering import NeuralMastering
        mastering = NeuralMastering(sample_rate=44100)
        audio = np.random.randn(2, 44100 * 5).astype(np.float32) * 0.8
        mastered = mastering.master(audio, target_lufs=-14.0)
        assert mastered.shape == audio.shape
        assert np.abs(mastered).max() <= 1.0

    def test_mastering_true_peak(self):
        from core.mixing.mastering import NeuralMastering
        mastering = NeuralMastering(sample_rate=44100)
        # Loud audio that would clip without limiting
        audio = np.random.randn(2, 44100 * 3).astype(np.float32) * 2.0
        mastered = mastering.master(audio)
        assert np.abs(mastered).max() <= 1.0 + 1e-4
