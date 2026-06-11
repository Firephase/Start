"""
FMA (Free Music Archive) Large dataset loader.

Supports FMA Large (106 k tracks) for music generation / captioning tasks.

Reference: Defferrard et al., "FMA: A Dataset for Music Analysis" (ISMIR 2017).
"""

import logging
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import torch
import torch.nn.functional as F
from torch import Tensor
from torch.utils.data import Dataset

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

# Genre mood / character associations used for richer text generation
_GENRE_DESCRIPTORS: Dict[str, List[str]] = {
    "Hip-Hop": ["rhythmic", "urban", "beat-driven"],
    "Pop": ["catchy", "melodic", "upbeat"],
    "Rock": ["energetic", "guitar-driven", "powerful"],
    "Electronic": ["synthesized", "electronic", "atmospheric"],
    "Experimental": ["avant-garde", "unconventional", "abstract"],
    "Folk": ["acoustic", "intimate", "storytelling"],
    "Classical": ["orchestral", "formal", "composed"],
    "Jazz": ["improvisational", "swing", "complex harmony"],
    "Country": ["twangy", "narrative", "heartfelt"],
    "Spoken": ["spoken word", "narrative", "non-musical"],
    "International": ["world music", "ethnic", "traditional"],
    "Blues": ["bluesy", "soulful", "expressive"],
    "Soul-RnB": ["soulful", "rhythm and blues", "smooth"],
    "Instrumental": ["instrumental", "melodic", "wordless"],
    "Old-Time / Historic": ["vintage", "historical", "classic"],
    "Easy Listening": ["relaxing", "smooth", "background"],
}


def _genre_to_descriptors(genre: str) -> str:
    for key, descs in _GENRE_DESCRIPTORS.items():
        if key.lower() in genre.lower():
            return random.choice(descs)
    return "musical"


def _build_text_description(
    title: str,
    artist: str,
    genre: str,
    tags: str,
    duration: float,
) -> str:
    """
    Generate a natural-language description from FMA track metadata.

    Examples:
        "a rhythmic hip-hop track by DJ Foo with themes of street, hustle"
        "an acoustic folk piece by Jane Smith"
    """
    parts: List[str] = []

    descriptor = _genre_to_descriptors(genre) if genre else "musical"
    genre_label = genre.lower() if genre else "music"
    parts.append(f"a {descriptor} {genre_label} track")

    if artist and artist.strip().lower() not in ("", "unknown"):
        parts.append(f"by {artist.strip()}")

    if tags:
        tag_list = [t.strip() for t in tags.replace(";", ",").split(",") if t.strip()]
        tag_list = [t for t in tag_list if len(t) > 2][:4]
        if tag_list:
            parts.append("featuring " + ", ".join(tag_list))

    description = " ".join(parts)

    # Capitalise sentence
    if description:
        description = description[0].upper() + description[1:]

    return description


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class FMADataset(Dataset):
    """
    PyTorch Dataset for FMA Large (106 k tracks).

    Directory layout expected::

        {root}/
          tracks/
            000/
              000002.mp3
              000005.mp3
              ...
            001/
              001000.mp3
              ...
          metadata/
            tracks.csv
            genres.csv

    Returns dicts with keys:

    =================  ==========================  ===================================
    Key                Type / Shape                Description
    =================  ==========================  ===================================
    audio              Tensor (1, segment_samples) Mono float32 waveform
    text_description   str                         Auto-generated text prompt
    genre              str                         Primary genre label
    duration           float                       Actual clip length in seconds
    =================  ==========================  ===================================

    Args:
        root: Path to the FMA dataset root directory.
        split: "train", "val", or "test" (uses FMA's official splits).
        sample_rate: Audio sample rate. Files are resampled if needed.
        segment_duration: Duration of audio segments in seconds.
        max_samples: Limit dataset to this many tracks (useful for debugging).
        transform: Optional callable applied to the returned dict.
        cache_metadata: Cache parsed metadata DataFrame in memory.
        seed: Random seed for reproducibility of segment cropping.
    """

    SEGMENT_DURATION: float = 30.0

    def __init__(
        self,
        root: Union[str, Path],
        split: str = "train",
        sample_rate: int = 22050,
        segment_duration: float = 30.0,
        max_samples: Optional[int] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        cache_metadata: bool = True,
        seed: int = 42,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.sample_rate = sample_rate
        self.segment_samples = int(segment_duration * sample_rate)
        self.transform = transform
        self.seed = seed

        self._items: List[Dict[str, Any]] = []
        self._genre_map: Dict[int, str] = {}
        self._load_metadata(max_samples)

    # ------------------------------------------------------------------
    # Metadata loading
    # ------------------------------------------------------------------

    def _load_metadata(self, max_samples: Optional[int]) -> None:
        tracks_csv = self.root / "metadata" / "tracks.csv"
        genres_csv = self.root / "metadata" / "genres.csv"

        if not tracks_csv.exists():
            log.warning(
                "FMA tracks.csv not found at %s. "
                "Set root to the directory containing metadata/ and tracks/",
                tracks_csv,
            )
            self._items = []
            return

        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("pandas is required to load FMA metadata.") from exc

        # Load genre mapping
        if genres_csv.exists():
            genres_df = pd.read_csv(genres_csv, index_col=0)
            self._genre_map = genres_df["title"].to_dict()

        # Load tracks; FMA uses 2-level column headers
        tracks = pd.read_csv(tracks_csv, index_col=0, header=[0, 1])

        # Filter by split
        split_col = ("set", "split")
        if split_col in tracks.columns:
            tracks = tracks[tracks[split_col] == self.split]

        loaded = 0
        for track_id, row in tracks.iterrows():
            audio_path = self._track_path(int(track_id))
            if not audio_path.exists():
                continue

            genre = self._get_genre(row)
            title = self._safe_get(row, ("track", "title"), "")
            artist = self._safe_get(row, ("artist", "name"), "")
            tags = self._safe_get(row, ("track", "tags"), "")
            native_duration = float(self._safe_get(row, ("track", "duration"), 0.0) or 0.0)

            text = _build_text_description(
                title=str(title),
                artist=str(artist),
                genre=genre,
                tags=str(tags),
                duration=native_duration,
            )

            self._items.append(
                {
                    "path": audio_path,
                    "track_id": int(track_id),
                    "genre": genre,
                    "text": text,
                    "native_duration": native_duration,
                }
            )
            loaded += 1
            if max_samples is not None and loaded >= max_samples:
                break

        log.info(
            "[FMA] %d/%d tracks loaded (split=%s, sr=%d)",
            len(self._items),
            loaded,
            self.split,
            self.sample_rate,
        )

    def _track_path(self, track_id: int) -> Path:
        tid_str = f"{track_id:06d}"
        return self.root / "tracks" / tid_str[:3] / f"{tid_str}.mp3"

    def _get_genre(self, row: Any) -> str:
        try:
            genre_id = int(row[("track", "genre_top")])
            return self._genre_map.get(genre_id, str(genre_id))
        except (KeyError, ValueError, TypeError):
            pass
        try:
            genre_id = int(row[("track", "genres_all")].strip("[]").split(",")[0])
            return self._genre_map.get(genre_id, "Unknown")
        except Exception:
            return "Unknown"

    @staticmethod
    def _safe_get(row: Any, key: Any, default: Any = "") -> Any:
        try:
            val = row[key]
            if val != val:  # NaN check
                return default
            return val
        except (KeyError, TypeError):
            return default

    # ------------------------------------------------------------------
    # Dataset protocol
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = self._items[idx]
        audio = self._load_audio(item["path"])

        sample = {
            "audio": audio,
            "text_description": item["text"],
            "genre": item["genre"],
            "duration": audio.shape[-1] / self.sample_rate,
        }

        if self.transform is not None:
            sample = self.transform(sample)

        return sample

    # ------------------------------------------------------------------
    # Audio loading
    # ------------------------------------------------------------------

    def _load_audio(self, path: Path) -> Tensor:
        """
        Load an audio file, resample to self.sample_rate, convert to mono,
        and extract a random 30-second segment.

        Returns:
            Float32 tensor of shape (1, segment_samples).
        """
        try:
            waveform, sr = self._backend_load(path)
            # Convert to mono
            if waveform.size(0) > 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            elif waveform.dim() == 1:
                waveform = waveform.unsqueeze(0)

            # Resample
            if sr != self.sample_rate:
                try:
                    import torchaudio
                    waveform = torchaudio.functional.resample(waveform, sr, self.sample_rate)
                except ImportError:
                    waveform = self._numpy_resample(waveform, sr, self.sample_rate)

            # Random segment
            total_samples = waveform.size(-1)
            if total_samples >= self.segment_samples:
                max_start = total_samples - self.segment_samples
                start = random.randint(0, max_start)
                waveform = waveform[:, start : start + self.segment_samples]
            else:
                waveform = F.pad(waveform, (0, self.segment_samples - total_samples))

            return waveform.float()  # (1, segment_samples)

        except Exception as exc:
            log.warning("Failed to load %s: %s. Returning silence.", path, exc)
            return torch.zeros(1, self.segment_samples, dtype=torch.float32)

    @staticmethod
    def _backend_load(path: Path):
        """Try multiple backends for robust audio loading."""
        last_exc = None

        # torchaudio is preferred (supports mp3 via ffmpeg/sox backend)
        try:
            import torchaudio
            return torchaudio.load(str(path))
        except Exception as exc:
            last_exc = exc

        # soundfile fallback (wav/flac only)
        try:
            import soundfile as sf
            import torch
            audio_np, sr = sf.read(str(path), dtype="float32", always_2d=True)
            return torch.from_numpy(audio_np.T), sr
        except Exception as exc:
            last_exc = exc

        raise RuntimeError(f"Could not load {path}: {last_exc}")

    @staticmethod
    def _numpy_resample(waveform: Tensor, src_sr: int, tgt_sr: int) -> Tensor:
        """Resample using scipy if torchaudio is not available."""
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(src_sr, tgt_sr)
        up, down = tgt_sr // g, src_sr // g
        audio_np = waveform.squeeze(0).numpy()
        resampled = resample_poly(audio_np, up, down).astype(np.float32)
        return torch.from_numpy(resampled).unsqueeze(0)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_genre_counts(self) -> Dict[str, int]:
        """Return a frequency table of genre labels in the loaded split."""
        counts: Dict[str, int] = {}
        for item in self._items:
            g = item["genre"]
            counts[g] = counts.get(g, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    def get_track_path(self, track_id: int) -> Path:
        """Return the expected path for a track by its FMA track ID."""
        return self._track_path(track_id)

    @property
    def genres(self) -> List[str]:
        """Sorted list of unique genre labels present in this split."""
        return sorted({item["genre"] for item in self._items})
