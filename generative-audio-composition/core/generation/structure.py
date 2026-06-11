# Song structure: verse, chorus, bridge, intro, outro
# Structures are lists of SongSection objects

from dataclasses import dataclass, field
from typing import Optional
import re
import math

STRUCTURE_PRESETS = {
    "standard": ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"],
    "short": ["verse", "chorus", "verse", "chorus"],
    "extended": [
        "intro",
        "verse",
        "pre-chorus",
        "chorus",
        "verse",
        "pre-chorus",
        "chorus",
        "bridge",
        "chorus",
        "chorus",
        "outro",
    ],
}

# Approximate bars per section type
SECTION_BARS: dict[str, int] = {
    "intro": 8,
    "verse": 16,
    "pre-chorus": 8,
    "chorus": 16,
    "bridge": 8,
    "outro": 8,
}

# Average syllables per second for sung vocals
_SYLLABLES_PER_SECOND_AT_120BPM = 2.5


@dataclass
class SongSection:
    section_type: str  # verse, chorus, bridge, intro, outro, pre-chorus
    lyrics: str
    start_time: float  # in seconds
    end_time: float
    f0_contour: Optional[object] = None  # numpy array


def _count_syllables(text: str) -> int:
    """Rough syllable counter based on vowel cluster detection."""
    text = text.lower().strip()
    # Remove punctuation
    text = re.sub(r"[^a-z\s']", "", text)
    count = 0
    vowels = "aeiouy"
    for word in text.split():
        word_syllables = 0
        prev_is_vowel = False
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_is_vowel:
                word_syllables += 1
            prev_is_vowel = is_vowel
        # Every word has at least one syllable
        count += max(1, word_syllables)
    return count


class SongStructurePlanner:
    def __init__(self):
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan_from_lyrics(
        self, lyrics: str, target_duration: float = 180.0
    ) -> list[SongSection]:
        """Auto-detect structure from LLM-generated lyrics with [Verse]/[Chorus] markers.

        Parameters
        ----------
        lyrics:
            Raw lyrics string with section markers such as ``[Verse 1]``,
            ``[Chorus]``, ``[Bridge]``, etc.
        target_duration:
            Total desired song length in seconds (used for padding/repeating).

        Returns
        -------
        list[SongSection]
            Ordered list of song sections with timing assigned.
        """
        sections_dict = self.lyrics_to_sections(lyrics)
        if not sections_dict:
            # Treat the whole string as a single verse
            sections_dict = {"verse": [lyrics.strip()]}

        # Build an ordered sequence preserving appearance order
        ordered_sequence: list[tuple[str, str]] = []
        seen: dict[str, int] = {}

        # Re-parse to preserve ordering
        pattern = re.compile(
            r"\[([^\]]+)\]",
            re.IGNORECASE,
        )
        current_type: Optional[str] = None
        current_lines: list[str] = []

        for line in lyrics.splitlines():
            m = pattern.match(line.strip())
            if m:
                if current_type is not None and current_lines:
                    ordered_sequence.append(
                        (current_type, "\n".join(current_lines).strip())
                    )
                current_type = self._normalize_section_name(m.group(1))
                current_lines = []
            else:
                if current_type is not None:
                    current_lines.append(line)

        if current_type is not None and current_lines:
            ordered_sequence.append(
                (current_type, "\n".join(current_lines).strip())
            )

        if not ordered_sequence:
            ordered_sequence = [("verse", lyrics.strip())]

        # Estimate duration for each section
        # We use a default BPM of 120 for estimation purposes
        bpm = 120.0
        raw_sections = []
        for sec_type, sec_lyrics in ordered_sequence:
            dur = self.estimate_section_duration(sec_lyrics, bpm)
            raw_sections.append(
                SongSection(
                    section_type=sec_type,
                    lyrics=sec_lyrics,
                    start_time=0.0,
                    end_time=dur,
                )
            )

        raw_sections = self.repeat_to_fill(raw_sections, target_duration)
        return self._assign_timings(raw_sections)

    def plan_from_spec(
        self,
        structure_spec: list[str],
        lyrics_by_section: dict,
        target_duration: float,
    ) -> list[SongSection]:
        """Build structure from user-provided spec.

        Parameters
        ----------
        structure_spec:
            Ordered list of section names, e.g. ``['verse', 'chorus', 'verse', 'chorus']``.
        lyrics_by_section:
            Mapping of section name -> lyrics string (or list of strings for
            numbered repeats).
        target_duration:
            Total desired song length in seconds.

        Returns
        -------
        list[SongSection]
            Ordered list of song sections with timing assigned.
        """
        bpm = 120.0
        raw_sections: list[SongSection] = []
        repeat_counters: dict[str, int] = {}

        for sec_type in structure_spec:
            normalized = self._normalize_section_name(sec_type)
            repeat_counters[normalized] = repeat_counters.get(normalized, 0) + 1
            idx = repeat_counters[normalized] - 1  # zero-based

            lyrics = ""
            if normalized in lyrics_by_section:
                val = lyrics_by_section[normalized]
                if isinstance(val, list):
                    lyrics = val[idx] if idx < len(val) else val[-1]
                else:
                    lyrics = val
            elif sec_type in lyrics_by_section:
                val = lyrics_by_section[sec_type]
                if isinstance(val, list):
                    lyrics = val[idx] if idx < len(val) else val[-1]
                else:
                    lyrics = val

            dur = self.estimate_section_duration(lyrics, bpm)
            raw_sections.append(
                SongSection(
                    section_type=normalized,
                    lyrics=lyrics,
                    start_time=0.0,
                    end_time=dur,
                )
            )

        raw_sections = self.repeat_to_fill(raw_sections, target_duration)
        return self._assign_timings(raw_sections)

    def estimate_section_duration(self, lyrics: str, bpm: float) -> float:
        """Estimate how long a section takes based on syllable count and BPM.

        Uses the heuristic that at 120 BPM, roughly 2.5 syllables are sung per
        second.  This scales linearly with BPM.

        Parameters
        ----------
        lyrics:
            Lyrics text for the section.
        bpm:
            Beats per minute of the song.

        Returns
        -------
        float
            Estimated duration in seconds (minimum 4 seconds).
        """
        if not lyrics or not lyrics.strip():
            # Instrumental section: assume 8 bars
            beats_per_bar = 4
            bars = 8
            return (bars * beats_per_bar) / max(bpm, 1.0) * 60.0

        syllables = _count_syllables(lyrics)
        syllables_per_second = _SYLLABLES_PER_SECOND_AT_120BPM * (bpm / 120.0)
        duration = syllables / max(syllables_per_second, 0.1)

        # Snap to nearest bar (4 beats) so duration is musically sensible
        beats_per_second = bpm / 60.0
        beats = duration * beats_per_second
        bars = max(2, math.ceil(beats / 4))
        snapped_duration = (bars * 4) / beats_per_second

        return max(snapped_duration, 4.0)

    def repeat_to_fill(
        self, sections: list[SongSection], target_duration: float
    ) -> list[SongSection]:
        """Repeat sections if content is too short for target duration.

        The sections are repeated cyclically until the cumulative duration
        reaches or exceeds ``target_duration``.

        Parameters
        ----------
        sections:
            Current section list.
        target_duration:
            Minimum total duration in seconds.

        Returns
        -------
        list[SongSection]
            Possibly extended section list (with duplicated sections).
        """
        if not sections:
            return sections

        current_total = sum(
            (s.end_time - s.start_time) if s.end_time > s.start_time else 0.0
            for s in sections
        )

        # Recompute using estimated durations stored in end_time only
        durations = [s.end_time for s in sections]  # end_time = duration before assign
        current_total = sum(durations)

        if current_total >= target_duration:
            return list(sections)

        result = list(sections)
        idx = 0
        while sum(s.end_time for s in result) < target_duration:
            src = sections[idx % len(sections)]
            result.append(
                SongSection(
                    section_type=src.section_type,
                    lyrics=src.lyrics,
                    start_time=0.0,
                    end_time=src.end_time,
                )
            )
            idx += 1

        return result

    def lyrics_to_sections(self, raw_lyrics: str) -> dict[str, list[str]]:
        """Parse [Verse 1], [Chorus], etc. markers into section dict.

        Parameters
        ----------
        raw_lyrics:
            Raw lyrics string containing section markers in square brackets.

        Returns
        -------
        dict[str, list[str]]
            Mapping of normalised section name to list of lyrics blocks
            (multiple blocks if the same section type appears more than once).
        """
        pattern = re.compile(r"\[([^\]]+)\]", re.IGNORECASE)
        result: dict[str, list[str]] = {}

        current_type: Optional[str] = None
        current_lines: list[str] = []

        def _flush():
            if current_type is not None:
                text = "\n".join(current_lines).strip()
                if text:
                    result.setdefault(current_type, []).append(text)

        for line in raw_lyrics.splitlines():
            m = pattern.match(line.strip())
            if m:
                _flush()
                current_type = self._normalize_section_name(m.group(1))
                current_lines = []
            else:
                if current_type is not None:
                    current_lines.append(line)

        _flush()
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_section_name(self, raw: str) -> str:
        """Convert 'Verse 1', 'PRE-CHORUS', etc. to canonical lowercase name."""
        name = raw.strip().lower()
        # Remove trailing numbers: "verse 1" -> "verse"
        name = re.sub(r"\s+\d+$", "", name)
        # Normalise dashes/spaces
        name = re.sub(r"[\s_]+", "-", name)
        return name

    def _assign_timings(self, sections: list[SongSection]) -> list[SongSection]:
        """Assign start_time / end_time sequentially.

        Before calling this method the ``end_time`` field is expected to hold
        the *duration* of the section (as produced by
        :meth:`estimate_section_duration`).
        """
        cursor = 0.0
        result: list[SongSection] = []
        for sec in sections:
            dur = sec.end_time  # duration stored here before assignment
            result.append(
                SongSection(
                    section_type=sec.section_type,
                    lyrics=sec.lyrics,
                    start_time=cursor,
                    end_time=cursor + dur,
                    f0_contour=sec.f0_contour,
                )
            )
            cursor += dur
        return result
