"""app.api.routes.dashboard._stat_card — week-over-week growth math, DB-free."""
from app.api.routes.dashboard import _stat_card


def test_no_baseline_omits_trend():
    assert _stat_card("Actors", 5, 5, 0).trend_pct is None


def test_no_new_rows_is_zero_growth_not_minus_100():
    assert _stat_card("Actors", 357, 0, 357).trend_pct == 0.0


def test_growth_is_relative_to_pre_window_baseline():
    assert _stat_card("Actors", 120, 20, 100).trend_pct == 20.0
