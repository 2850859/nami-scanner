from __future__ import annotations

import pandas as pd

from trade_rules.backtest_engine import (
    Backtester,
    SignalDetector,
    StrategyConfig,
    Trade,
    calculate_metrics,
    trades_to_dataframe,
)


def test_perfect_order_column():
    idx = pd.date_range("2024-01-02", periods=30, freq="B")
    close = pd.Series(range(100, 130), index=idx, dtype=float)
    ohlcv = pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1_000_000,
        },
        index=idx,
    )
    topix = pd.DataFrame({"close": close}, index=idx)
    d = SignalDetector(StrategyConfig(strategy_rules="v2")).calculate_indicators(
        ohlcv, topix, market="JP"
    )
    assert "sma10" in d.columns
    assert "perfect_order" in d.columns
    assert bool(d["perfect_order"].iloc[-1])


def test_calculate_indicators_has_expected_columns(sample_ohlcv_and_topix):
    ohlcv, topix = sample_ohlcv_and_topix
    cfg = StrategyConfig(strategy_rules="v2", market="JP")
    det = SignalDetector(cfg)
    d = det.calculate_indicators(ohlcv, topix, market="JP")
    for col in (
        "sma20",
        "sma10",
        "sma5",
        "sma60",
        "perfect_order",
        "rsi14",
        "sma20_dev",
        "screen_pass",
        "scr_v2_trend",
    ):
        assert col in d.columns


def test_detect_signals_runs_without_error(sample_ohlcv_and_topix):
    ohlcv, topix = sample_ohlcv_and_topix
    cfg = StrategyConfig(
        strategy_rules="cleartrade",
        require_volume_reexpand=False,
        max_positions=3,
        stop_loss_pct=0.05,
    )
    det = SignalDetector(cfg)
    d = det.calculate_indicators(ohlcv, topix)
    sigs = det.detect_signals(d)
    assert isinstance(sigs, list)


def test_backtester_run_completes(sample_ohlcv_and_topix):
    ohlcv, topix = sample_ohlcv_and_topix
    cfg = StrategyConfig(
        strategy_rules="cleartrade",
        require_volume_reexpand=False,
        max_positions=3,
        stop_loss_pct=0.05,
    )
    bt = Backtester(cfg, initial_capital=10_000_000.0)
    result = bt.run({"AAA.T": ohlcv.copy()}, topix.copy())
    assert "trades" in result
    assert "equity_curve" in result
    assert len(result["equity_curve"]) > 0


def test_calculate_metrics_empty_trades():
    eq = pd.DataFrame(
        {"equity": [1e8, 1e8]},
        index=pd.date_range("2024-01-02", periods=2, freq="B"),
    )
    out = calculate_metrics({"trades": [], "equity_curve": eq, "final_capital": 1e8}, 1e8)
    assert out.get("error") == "No trades executed"


def test_calculate_metrics_one_winning_trade():
    idx = pd.date_range("2024-01-02", periods=5, freq="B")
    eq = pd.DataFrame({"equity": [1e8, 1e8, 1_000_100_000.0, 1_000_100_000.0, 1_000_100_000.0]}, index=idx)
    t = Trade(
        code="X",
        entry_date=idx[1],
        exit_date=idx[2],
        entry_price=100.0,
        exit_price=110.0,
        shares=100,
        exit_reason="tp1_partial",
        pnl=1000.0,
        pnl_pct=0.1,
        holding_days=1,
        trade_group="X:2024-01-03",
        assumed_slippage_pct=0.1,
    )
    m = calculate_metrics(
        {"trades": [t], "equity_curve": eq, "final_capital": float(eq["equity"].iloc[-1])},
        1e8,
    )
    assert m["trade_count"] == 1
    assert m["win_rate_pct"] == 100.0


def test_trades_to_dataframe_empty():
    assert trades_to_dataframe([]).empty
