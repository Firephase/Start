"""
OpenSinger dataset loader for SVS (Singing Voice Synthesis) training.
"""

import json
import logging
import os
import pickle
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from torch import Tensor
from torch.utils.data import Dataset

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phoneme utilities
# ---------------------------------------------------------------------------

# Pinyin-to-phoneme mapping for Mandarin singing (simplified).
# In production, replace with full MFA output parsing.
PINYIN_INITIALS = [
    "b", "p", "m", "f", "d", "t", "n", "l",
    "g", "k", "h", "j", "q", "x", "zh", "ch",
    "sh", "r", "z", "c", "s", "y", "w",
]
PINYIN_FINALS = [
    "a", "o", "e", "i", "u", "v",
    "ai", "ei", "ui", "ao", "ou", "iu",
    "ie", "ve", "er", "an", "en", "in",
    "un", "vn", "ang", "eng", "ing", "ong",
]
SILENCE_PHONEME = "SP"
SPECIAL_PHONEMES = [SILENCE_PHONEME, "<pad>", "<unk>"]
ALL_PHONEMES = SPECIAL_PHONEMES + PINYIN_INITIALS + PINYIN_FINALS
PHONEME_TO_ID = {p: i for i, p in enumerate(ALL_PHONEMES)}
UNK_ID = PHONEME_TO_ID["<unk>"]
PAD_ID = PHONEME_TO_ID["<pad>"]


def phoneme_to_id(phoneme: str) -> int:
    return PHONEME_TO_ID.get(phoneme, UNK_ID)


def text_to_phoneme_ids(text: str) -> List[int]:
    """
    Naively split a text line (space-separated phonemes or lyrics)
    into phoneme IDs.

    In a full system, replace with MFA TextGrid parsing.
    """
    tokens = text.strip().split()
    return [phoneme_to_id(t) for t in tokens] if tokens else [UNK_ID]


# ---------------------------------------------------------------------------
# MFA TextGrid parser
# ---------------------------------------------------------------------------

def _parse_textgrid(tg_path: Path) -> List[Tuple[float, float, str]]:
    """
    Parse a Praat TextGrid file produced by the Montreal Forced Aligner.

    Returns:
        List of (start_sec, end_sec, phoneme) tuples sorted by start time.
    """
    alignments: List[Tuple[float, float, str]] = []
    try:
        with open(tg_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        log.warning("Could not read TextGrid %s: %s", tg_path, exc)
        return alignments

    # Locate the "phones" tier
    phones_start = content.find('"phones"')
    if phones_start == -1:
        phones_start = content.find('"phone"')
    if phones_start == -1:
        return alignments

    tier_content = content[phones_start:]
    lines = tier_content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("xmin"):
            try:
                xmin = float(line.split("=")[1].strip())
                xmax = float(lines[i + 1].strip().split("=")[1].strip())
                text_line = lines[i + 2].strip()
                phoneme = text_line.split("=")[1].strip().strip('"')
                if phoneme and phoneme != "":
                    alignments.append((xmin, xmax, phoneme))
                i += 3
            except (IndexError, ValueError):
                i += 1
        else:
            i += 1

    return sorted(alignments, key=lambda x: x[0])


# ---------------------------------------------------------------------------
# Feature extractor
# ---------------------------------------------------------------------------

def _extract_f0(
    audio: np.ndarray,
    sr: int,
    hop_length: int = 512,
    f0_min: float = 50.0,
    f0_max: float = 1100.0,
) -> np.ndarray:
    """
    Extract fundamental frequency (F0) contour using pyworld HARVEST.

    Falls back to librosa pyin if pyworld is unavailable.
    """
    try:
        import pyworld as pw
        audio_d = audio.astype(np.float64)
        f0, t = pw.harvest(
            audio_d,
            sr,
            f0_floor=f0_min,
            f0_ceil=f0_max,
            frame_period=1000.0 * hop_length / sr,
        )
        return f0.astype(np.float32)
    except ImportError:
        pass

    try:
        import librosa
        f0, voiced, _ = librosa.pyin(
            audio,
            fmin=f0_min,
            fmax=f0_max,
            sr=sr,
            hop_length=hop_length,
        )
        f0 = np.where(voiced, f0, 0.0)
        return f0.astype(np.float32)
    except ImportError as exc:
        raise RuntimeError(
            "Install pyworld or librosa for F0 extraction."
        ) from exc


def _extract_energy(
    audio: np.ndarray,
    hop_length: int = 512,
    n_fft: int = 2048,
) -> np.ndarray:
    """Frame-wise RMS energy."""
    try:
        import librosa
        return librosa.feature.rms(
            y=audio, frame_length=n_fft, hop_length=hop_length
        ).squeeze(0).astype(np.float32)
    except ImportError:
        # Manual RMS
        frames = int(np.floor((len(audio) - n_fft) / hop_length)) + 1
        energy = np.array(
            [
                np.sqrt(np.mean(audio[i * hop_length : i * hop_length + n_fft] ** 2))
                for i in range(frames)
            ],
            dtype=np.float32,
        )
        return energy


def _extract_mel(
    audio: np.ndarray,
    sr: int,
    n_mels: int = 80,
    n_fft: int = 2048,
    hop_length: int = 512,
    f_min: float = 0.0,
    f_max: Optional[float] = None,
) -> np.ndarray:
    try:
        import librosa
        mel = librosa.feature.melspectrogram(
            y=audio,
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=n_mels,
            fmin=f_min,
            fmax=f_max or sr / 2,
            power=2.0,
        )
        mel_db = librosa.power_to_db(mel, ref=np.max, top_db=80.0)
        return mel_db.astype(np.float32)
    except ImportError as exc:
        raise RuntimeError("librosa is required for mel extraction.") from exc


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class OpenSingerDataset(Dataset):
    """
    PyTorch Dataset for the OpenSinger corpus.

    Expected directory structure::

        {root}/
          {singer_id}/
            {song_name}/
              {sentence_id}.wav
              {sentence_id}.txt        # space-separated phoneme labels
              {sentence_id}.TextGrid   # optional MFA alignment output

    Each sample dict returned by __getitem__ contains:

    =========  ==========================  ==================================
    Key        Shape                       Description
    =========  ==========================  ==================================
    audio      (T,)                        Raw float32 waveform
    mel        (n_mels, frames)            Log-mel spectrogram
    f0         (frames,)                   F0 contour in Hz (0 = unvoiced)
    energy     (frames,)                   RMS energy per frame
    duration   (n_phonemes,)               Duration of each phoneme in frames
    phonemes   (n_phonemes,)               Phoneme ID sequence
    speaker_id Scalar LongTensor           Integer speaker index
    singer_id  str                         Singer directory name
    =========  ==========================  ==================================

    Args:
        root: Path to the OpenSinger root directory.
        sample_rate: Audio sample rate. Files are resampled if needed.
        n_mels: Number of mel filter banks.
        n_fft: FFT size.
        hop_length: Hop size in samples.
        f_min: Minimum frequency for mel filterbank.
        f_max: Maximum frequency for mel filterbank.
        use_mfa: If True, parse .TextGrid MFA output for durations.
                 Falls back to uniform durations if TextGrid is missing.
        cache_dir: Directory to cache processed features (pickle).
                   Set to None to disable caching.
        transform: Optional callable applied to the returned dict.
        split: "train", "val", or "test" (for metadata/sampling purposes only).
        val_fraction: Fraction of singers held out for validation.
        seed: Random seed for train/val split.
    """

    def __init__(
        self,
        root: Union[str, Path],
        sample_rate: int = 44100,
        n_mels: int = 80,
        n_fft: int = 2048,
        hop_length: int = 512,
        f_min: float = 0.0,
        f_max: Optional[float] = None,
        use_mfa: bool = True,
        cache_dir: Optional[Union[str, Path]] = None,
        transform: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        split: str = "train",
        val_fraction: float = 0.1,
        seed: int = 42,
    ) -> None:
        self.root = Path(root)
        self.sample_rate = sample_rate
        self.n_mels = n_mels
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.f_min = f_min
        self.f_max = f_max or sample_rate / 2.0
        self.use_mfa = use_mfa
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.transform = transform
        self.split = split

        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Build speaker index
        self._singer_to_id: Dict[str, int] = {}
        self._items: List[Dict[str, Path]] = []
        self._build_index(val_fraction, seed)

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_index(self, val_fraction: float, seed: int) -> None:
        """Scan directory tree and build the flat item list."""
        singer_dirs = sorted(
            d for d in self.root.iterdir() if d.is_dir()
        )
        rng = np.random.RandomState(seed)
        n_val = max(1, int(len(singer_dirs) * val_fraction))
        val_indices = set(rng.choice(len(singer_dirs), n_val, replace=False))

        for idx, singer_dir in enumerate(singer_dirs):
            is_val = idx in val_indices
            if self.split == "train" and is_val:
                continue
            if self.split == "val" and not is_val:
                continue

            singer_id = singer_dir.name
            if singer_id not in self._singer_to_id:
                self._singer_to_id[singer_id] = len(self._singer_to_id)

            for song_dir in sorted(singer_dir.iterdir()):
                if not song_dir.is_dir():
                    continue
                for wav_path in sorted(song_dir.glob("*.wav")):
                    txt_path = wav_path.with_suffix(".txt")
                    tg_path = wav_path.with_suffix(".TextGrid")
                    self._items.append(
                        {
                            "wav": wav_path,
                            "txt": txt_path,
                            "tg": tg_path if tg_path.exists() else None,
                            "singer_id": singer_id,
                        }
                    )

        log.info(
            "[OpenSinger] %d items (%s), %d unique singers",
            len(self._items),
            self.split,
            len(self._singer_to_id),
        )

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, wav_path: Path) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        rel = wav_path.relative_to(self.root)
        key = str(rel).replace(os.sep, "_").replace(".", "_")
        return self.cache_dir / f"{key}.pkl"

    def _load_from_cache(self, cache_path: Path) -> Optional[Dict[str, Any]]:
        if cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception as exc:
                log.warning("Cache read failed (%s): %s", cache_path, exc)
        return None

    def _save_to_cache(self, cache_path: Path, data: Dict[str, Any]) -> None:
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            log.warning("Cache write failed (%s): %s", cache_path, exc)

    # ------------------------------------------------------------------
    # Feature computation
    # ------------------------------------------------------------------

    def _compute_features(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Load audio and compute all features."""
        wav_path: Path = item["wav"]
        txt_path: Path = item["txt"]
        tg_path: Optional[Path] = item["tg"]
        singer_id: str = item["singer_id"]

        # Load audio
        try:
            import soundfile as sf
            audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
        except Exception:
            try:
                import torchaudio
                waveform, sr = torchaudio.load(str(wav_path))
                audio = waveform.mean(0).numpy()
            except Exception as exc:
                raise RuntimeError(f"Cannot load {wav_path}: {exc}") from exc

        # Resample
        if sr != self.sample_rate:
            try:
                import librosa
                audio = librosa.resample(audio, orig_sr=sr, target_sr=self.sample_rate)
            except ImportError:
                from scipy.signal import resample
                ratio = self.sample_rate / sr
                audio = resample(audio, int(len(audio) * ratio)).astype(np.float32)
            sr = self.sample_rate

        # Convert to mono if needed
        if audio.ndim > 1:
            audio = audio.mean(axis=-1)
        audio = audio.astype(np.float32)

        # Mel spectrogram
        mel = _extract_mel(
            audio, sr,
            n_mels=self.n_mels,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            f_min=self.f_min,
            f_max=self.f_max,
        )  # (n_mels, T_frames)
        n_frames = mel.shape[1]

        # F0 contour
        f0 = _extract_f0(audio, sr, hop_length=self.hop_length)
        f0 = _align_length(f0, n_frames)

        # Energy
        energy = _extract_energy(audio, hop_length=self.hop_length, n_fft=self.n_fft)
        energy = _align_length(energy, n_frames)

        # Phonemes and durations
        phoneme_ids, durations = self._get_alignment(
            txt_path, tg_path, n_frames, sr
        )

        return {
            "audio": audio,
            "mel": mel,
            "f0": f0,
            "energy": energy,
            "duration": np.array(durations, dtype=np.float32),
            "phonemes": np.array(phoneme_ids, dtype=np.int64),
            "speaker_id": self._singer_to_id[singer_id],
            "singer_id": singer_id,
        }

    def _get_alignment(
        self,
        txt_path: Path,
        tg_path: Optional[Path],
        n_frames: int,
        sr: int,
    ) -> Tuple[List[int], List[float]]:
        """
        Return (phoneme_ids, durations_in_frames).

        Priority:
        1. MFA TextGrid (if use_mfa=True and .TextGrid exists)
        2. Uniform duration distribution from .txt phoneme list
        3. Single UNK token with full duration
        """
        if self.use_mfa and tg_path is not None and tg_path.exists():
            alignments = _parse_textgrid(tg_path)
            if alignments:
                ids = [phoneme_to_id(ph) for _, _, ph in alignments]
                durations = [
                    max(1, int(round((end - start) * sr / self.hop_length)))
                    for start, end, _ in alignments
                ]
                return ids, durations

        # Fall back to reading phoneme labels from .txt
        if txt_path.exists():
            try:
                text = txt_path.read_text(encoding="utf-8").strip()
                ids = text_to_phoneme_ids(text)
                if ids:
                    n_ph = len(ids)
                    base_dur = n_frames // n_ph
                    rem = n_frames % n_ph
                    durations = [base_dur + (1 if i < rem else 0) for i in range(n_ph)]
                    return ids, durations
            except Exception as exc:
                log.warning("Could not read text file %s: %s", txt_path, exc)

        return [UNK_ID], [n_frames]

    # ------------------------------------------------------------------
    # Dataset protocol
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = self._items[idx]
        cache_path = self._cache_key(item["wav"])

        # Try cache
        if cache_path is not None:
            cached = self._load_from_cache(cache_path)
            if cached is not None:
                features = cached
            else:
                features = self._compute_features(item)
                self._save_to_cache(cache_path, features)
        else:
            features = self._compute_features(item)

        # Convert arrays to tensors
        sample: Dict[str, Any] = {
            "audio": torch.from_numpy(features["audio"]),
            "mel": torch.from_numpy(features["mel"]),
            "f0": torch.from_numpy(features["f0"]),
            "energy": torch.from_numpy(features["energy"]),
            "duration": torch.from_numpy(features["duration"]),
            "phonemes": torch.from_numpy(features["phonemes"]),
            "speaker_id": torch.tensor(features["speaker_id"], dtype=torch.long),
            "singer_id": features["singer_id"],
        }

        if self.transform is not None:
            sample = self.transform(sample)

        return sample

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @property
    def num_speakers(self) -> int:
        return len(self._singer_to_id)

    @property
    def num_phonemes(self) -> int:
        return len(ALL_PHONEMES)

    def get_singer_id(self, singer_name: str) -> int:
        return self._singer_to_id[singer_name]

    # ------------------------------------------------------------------
    # Public API aliases (spec-compatible names)
    # ------------------------------------------------------------------

    def _extract_features(self, audio: np.ndarray, sr: int) -> dict:
        """
        Public alias for ``_compute_features`` — extracts mel, F0, energy.

        This version accepts a pre-loaded waveform instead of a file-path dict,
        matching the interface described in the class docstring.

        Parameters
        ----------
        audio : np.ndarray
            Mono float32 waveform.
        sr : int
            Sample rate.

        Returns
        -------
        dict with keys:
            mel     : np.ndarray  (n_mels, T_frames)
            f0      : np.ndarray  (T_frames,)
            voiced  : np.ndarray  (T_frames,) bool
            energy  : np.ndarray  (T_frames,)
        """
        mel = _extract_mel(
            audio, sr,
            n_mels=self.n_mels,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            f_min=self.f_min,
            f_max=self.f_max,
        )
        n_frames = mel.shape[1]

        f0_arr = _extract_f0(audio, sr, hop_length=self.hop_length)
        f0_arr = _align_length(f0_arr, n_frames)
        voiced = (f0_arr > 0).astype(bool)

        energy = _extract_energy(audio, hop_length=self.hop_length, n_fft=self.n_fft)
        energy = _align_length(energy, n_frames)

        return {
            "mel": mel,
            "f0": f0_arr,
            "voiced": voiced,
            "energy": energy,
        }

    def _load_phoneme_alignment(
        self,
        lab_path: "Path",
    ) -> "Tuple[List[str], List[float]]":
        """
        Parse an MFA TextGrid or HTK .lab file into (phonemes, durations).

        Delegates to the module-level ``_parse_textgrid`` for .TextGrid files,
        and implements a simple HTK label reader for .lab files.

        Parameters
        ----------
        lab_path : Path
            Path to the alignment file (.TextGrid or .lab).

        Returns
        -------
        tuple[list[str], list[float]]
            ``(phoneme_list, duration_seconds)``  — duration per phoneme in
            seconds (NOT in frames; convert with ``sr / hop_length`` downstream).
        """
        lab_path = Path(lab_path)
        suffix = lab_path.suffix.lower()

        if suffix in {".textgrid", ".TextGrid"}:
            alignments = _parse_textgrid(lab_path)  # [(start, end, phoneme)]
            phonemes = [ph for _, _, ph in alignments]
            durations = [float(end - start) for start, end, _ in alignments]
            return phonemes, durations

        # HTK .lab format: start_100ns  end_100ns  phoneme
        phonemes: List[str] = []
        durations: List[float] = []
        try:
            lines = lab_path.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 3:
                    continue
                try:
                    start_raw = int(parts[0])
                    end_raw = int(parts[1])
                    ph = parts[2]
                except ValueError:
                    continue
                # HTK units are 100 ns; convert to seconds
                dur_sec = (end_raw - start_raw) * 1e-7
                phonemes.append(ph)
                durations.append(float(dur_sec))
        except Exception as exc:
            log.warning("Could not parse .lab file %s: %s", lab_path, exc)

        return phonemes, durations

    # ------------------------------------------------------------------
    # Collate function
    # ------------------------------------------------------------------

    @staticmethod
    def collate_fn(batch: "List[Dict[str, Any]]") -> "Dict[str, Any]":
        """
        Collate a list of samples from :meth:`__getitem__` into a padded batch.

        Variable-length tensors (audio, mel, f0, energy, phonemes, duration)
        are right-padded with zeros to the length of the longest element.
        Fixed scalars (speaker_id) are stacked directly.

        Parameters
        ----------
        batch : list[dict]
            List of sample dicts returned by ``__getitem__``.

        Returns
        -------
        dict
            Padded batch tensors plus ``audio_lengths``, ``mel_lengths``,
            and ``phoneme_lengths`` for attention masking.
        """
        import torch
        import torch.nn.functional as F

        def _pad_1d(tensors):
            lengths = torch.tensor([t.shape[-1] for t in tensors], dtype=torch.long)
            max_len = int(lengths.max().item())
            padded = torch.stack([F.pad(t, (0, max_len - t.shape[-1])) for t in tensors])
            return padded, lengths

        def _pad_2d(tensors):
            lengths = torch.tensor([t.shape[-1] for t in tensors], dtype=torch.long)
            max_len = int(lengths.max().item())
            padded = torch.stack([F.pad(t, (0, max_len - t.shape[-1])) for t in tensors])
            return padded, lengths

        audio_batch, audio_lengths = _pad_1d([s["audio"] for s in batch])
        mel_batch, mel_lengths = _pad_2d([s["mel"] for s in batch])
        f0_batch, _ = _pad_1d([s["f0"] for s in batch])
        energy_batch, _ = _pad_1d([s["energy"] for s in batch])
        ph_batch, ph_lengths = _pad_1d([s["phonemes"] for s in batch])
        dur_batch, _ = _pad_1d([s["duration"] for s in batch])

        return {
            "audio": audio_batch,
            "audio_lengths": audio_lengths,
            "mel": mel_batch,
            "mel_lengths": mel_lengths,
            "f0": f0_batch,
            "energy": energy_batch,
            "phonemes": ph_batch.long(),
            "phoneme_lengths": ph_lengths,
            "duration": dur_batch,
            "speaker_id": torch.stack([s["speaker_id"] for s in batch]),
            "singer_id": [s["singer_id"] for s in batch],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _align_length(arr: np.ndarray, target: int) -> np.ndarray:
    """Trim or zero-pad a 1-D array to the target length."""
    if len(arr) >= target:
        return arr[:target]
    return np.pad(arr, (0, target - len(arr)), mode="constant")
