
"""Unit tests for the rate-limiting algorithms."""

import pytest

from app.buckets import (
    TIERS,
    WINDOW,
    LimitError,
    boundary_burst,
    consume,
    fixed_window_allows,
    fixed_window_check,
    rate_per_second,
    refill,
    retry_after_fixed,
    sliding_counter_allows,
    sliding_counter_estimate,
    sliding_log_allows,
    sliding_log_check,
    sliding_log_count,
    tier,
    trim,
    window_id,
    window_start,
)


# Tier tests

def test_free_tier():
    result = tier("free")
    assert result["name"] == "free"
    assert result["per_minute"] == 5
    assert result["burst"] == 5


def test_basic_tier():
    assert tier("basic")["per_minute"] == 60


def test_pro_tier():
    assert tier("pro")["per_minute"] == 600


def test_unknown_tier_raises_error():
    with pytest.raises(LimitError):
        tier("unknown")


def test_tiers_are_available():
    assert "free" in TIERS
    assert "basic" in TIERS
    assert "pro" in TIERS


# Window tests

def test_rate_per_second():
    assert rate_per_second(60) == 1.0
    assert rate_per_second(600) == 10.0


def test_window_start():
    assert window_start(960.0) == 960.0
    assert window_start(1019.9) == 960.0
    assert window_start(1020.0) == 1020.0


def test_window_id():
    assert window_id(0) == 0
    assert window_id(59.999) == 0
    assert window_id(60.0) == 1


def test_window_constant():
    assert WINDOW > 0


def test_retry_after_fixed():
    assert retry_after_fixed(960.0) == 60.0
    assert retry_after_fixed(990.0) == 30.0


# Fixed-window tests

def test_fixed_window_allows_requests_under_limit():
    assert fixed_window_allows(0, 5) is True
    assert fixed_window_allows(4, 5) is True


def test_fixed_window_blocks_at_limit():
    assert fixed_window_allows(5, 5) is False


def test_fixed_window_check_allows_request():
    result = fixed_window_check([], 970.0, 3)
    assert result["allowed"] is True


def test_fixed_window_check_blocks_at_limit():
    result = fixed_window_check([961, 962, 963], 970.0, 3)
    assert result["allowed"] is False


def test_boundary_burst_has_two_windows_of_requests():
    timestamps = boundary_burst(10)
    assert len(timestamps) == 20


# Sliding-log tests

def test_trim_removes_old_timestamps():
    result = trim([0, 10, 50, 100], 100)
    assert result == [50.0, 100.0]


def test_sliding_log_count():
    assert sliding_log_count([90, 95, 99], 100) == 3


def test_sliding_log_allows_under_limit():
    assert sliding_log_allows([90, 95], 100, 3) is True


def test_sliding_log_blocks_at_limit():
    assert sliding_log_allows([90, 95, 99], 100, 3) is False


def test_sliding_log_check_allows_request():
    result = sliding_log_check([90, 95], 100, 3)
    assert result["allowed"] is True


def test_sliding_log_check_blocks_request():
    result = sliding_log_check([90, 95, 99], 100, 3)
    assert result["allowed"] is False


# Sliding-counter tests

def test_sliding_counter_estimate():
    result = sliding_counter_estimate(0, 2, 90, 60)
    assert result >= 0


def test_sliding_counter_allows_under_limit():
    assert sliding_counter_allows(1, 1, 90, 5) is True


def test_sliding_counter_blocks_at_limit():
    assert sliding_counter_allows(0, 5, 90, 5) is False


# Token-bucket tests

def test_refill_does_not_reduce_tokens():
    result = refill(5, 10, 1, 10, 20)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] >= 5


def test_consume_returns_result():
    result = consume(5, 10, 1, 10, 20)
    assert result is not None

# Boundary behavior

def test_boundary_burst_is_sorted():
    timestamps = boundary_burst(10)
    assert timestamps == sorted(timestamps)


def test_sliding_log_rejects_boundary_burst():
    timestamps = boundary_burst(10)
    recent_requests = timestamps[:10]
    assert sliding_log_allows(recent_requests, timestamps[10], 10) is False
