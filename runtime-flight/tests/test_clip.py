from runtime_flight.clip import (
    ALLOWED_VIDEO_DURATIONS_S,
    DEFAULT_VIDEO_DURATION_S,
    duration_window,
    infer_clip_duration_s,
    max_thought_chars,
    speech_target_s,
    writer_word_range,
)
from runtime_flight.harness_live import remaining_submit_slots


def test_live_default_is_fifteen_seconds_and_only_h3_presets_are_legal():
    assert DEFAULT_VIDEO_DURATION_S == 15
    assert ALLOWED_VIDEO_DURATIONS_S == (5, 10, 15)


def test_speech_and_character_budgets_scale_with_clip_length():
    assert speech_target_s(5) == 4.3
    assert speech_target_s(10) == 9.3
    assert speech_target_s(15) == 14.3
    assert max_thought_chars(5) == 120
    assert max_thought_chars(10) == 240
    assert max_thought_chars(15) == 360
    assert writer_word_range(5) == (8, 16)
    assert writer_word_range(15) == (24, 48)


def test_duration_window_keeps_the_same_slack_on_longer_takes():
    assert duration_window(5) == (4.7, 5.3)
    assert duration_window(15) == (14.7, 15.3)


def test_infer_clip_duration_from_writer_speech_target():
    assert infer_clip_duration_s(4.3) == 5
    assert infer_clip_duration_s(14.3) == 15


def test_ninety_second_show_fits_five_fifteen_second_takes():
    assert remaining_submit_slots(90, 0, clip_duration_s=15) == 5
    assert remaining_submit_slots(90, 0, clip_duration_s=5) == 17
