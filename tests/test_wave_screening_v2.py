from __future__ import annotations

import numpy as np
import pandas as pd

from trade_rules.backtest_engine import SignalDetector, StrategyConfig
from trade_rules.wave_screening_v2 import (
    add_v2_indicators,
    entry_pattern_41,
    entry_pattern_42,
    infer_market,
)


def test_infer_market():
    assert infer_market("8035.T") == "JP"
    assert infer_market("NVDA") == "US"


def test_v2_screening_uptrend(sample_ohlcv_and_topix):
    ohlcv, _ = sample_ohlcv_and_topix
    cfg = StrategyConfig(strategy_rules="v2", market="JP")
    d = add_v2_indicators(ohlcv, cfg)
    assert "rsi14" in d.columns
    assert "sma60" in d.columns
    assert bool(d["scr_v2_trend"].iloc[-1])
    assert not pd.isna(d["rsi14"].iloc[-1])


def test_entry_pattern_42_on_shallow_pullback():
    idx = pd.date_range("2024-01-02", periods=80, freq="B")
    close = pd.Series(np.linspace(100, 130, 80), index=idx)
    ohlcv = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(80, 2_000_000),
        },
        index=idx,
    )
    ohlcv.iloc[-3:, ohlcv.columns.get_loc("close")] -= [1.0, 0.5, 0.2]
    ohlcv.iloc[-3:, ohlcv.columns.get_loc("open")] = ohlcv.iloc[-3:]["close"] + 0.3
    cfg = StrategyConfig(strategy_rules="v2")
    d = add_v2_indicators(ohlcv, cfg)
    i = len(d) - 1
    assert entry_pattern_42(d, i, cfg) or entry_pattern_41(d, i, cfg)


def test_detect_signals_v2_runs(sample_ohlcv_and_topix):
    ohlcv, topix = sample_ohlcv_and_topix
    cfg = StrategyConfig(strategy_rules="v2", market="JP")
    det = SignalDetector(cfg)
    d = det.calculate_indicators(ohlcv, topix, market="JP")
    sigs = det.detect_signals(d, market="JP")
    assert isinstance(sigs, list)
