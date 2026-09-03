"""H3 Max clip-length presets and the budgets that scale with them."""

from __future__ import annotations

ALLOWED_VIDEO_DURATIONS_S = (5, 10, 15)
DEFAULT_VIDEO_DURATION_S = 15
DURATION_TOLERANCE_S = 0.3
SPEECH_SLACK_S = 0.7
CHARS_PER_5S = 120
WORDS_PER_5S = (8, 16)


def require_clip_duration_s(duration_s: int) -> int:
    if duration_s not in ALLOWED_VIDEO_DURATIONS_S:
        raise ValueError("video.duration_s must be 5, 10, or 15")
    return duration_s


def speech_target_s(clip_duration_s: int) -> float:
    require_clip_duration_s(clip_duration_s)
    return round(clip_duration_s - SPEECH_SLACK_S, 1)


def max_thought_chars(clip_duration_s: int) -> int:
    require_clip_duration_s(clip_duration_s)
    return CHARS_PER_5S * (clip_duration_s // 5)


def writer_word_range(clip_duration_s: int) -> tuple[int, int]:
    require_clip_duration_s(clip_duration_s)
    scale = clip_duration_s // 5
    return WORDS_PER_5S[0] * scale, WORDS_PER_5S[1] * scale


def duration_window(clip_duration_s: int) -> tuple[float, float]:
    require_clip_duration_s(clip_duration_s)
    return (
        clip_duration_s - DURATION_TOLERANCE_S,
        clip_duration_s + DURATION_TOLERANCE_S,
    )


def infer_clip_duration_s(speech_s: float) -> int:
    guessed = int(round(float(speech_s) + SPEECH_SLACK_S))
    if guessed in ALLOWED_VIDEO_DURATIONS_S:
        return guessed
    return min(ALLOWED_VIDEO_DURATIONS_S, key=lambda item: abs(item - guessed))
