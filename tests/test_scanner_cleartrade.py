from __future__ import annotations

from trade_rules.scanner_cleartrade import eligible_for_trading, enrich_scan_result


def test_eligible_for_trading():
    assert eligible_for_trading("S", True) is True
    assert eligible_for_trading("B", True) is False
    assert eligible_for_trading("S", False) is False


def test_enrich_scan_result_runs(sample_ohlcv_and_topix):
    ohlcv, topix = sample_ohlcv_and_topix
    out = enrich_scan_result(ohlcv, topix, ticker="7203.T")
    assert "trade_rules_candidate" in out
    assert "cleartrade_bonus" in out
    assert "cleartrade_flags" in out
    assert isinstance(out["cleartrade_bonus"], int)
    assert "wave_v2_screen_pass" in out
