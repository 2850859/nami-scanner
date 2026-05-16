"""
日次スキャン用: 波乗り v2.0 / cleartrade フィールド付与。
"""

from __future__ import annotations

import pandas as pd

from trade_rules.backtest_engine import SignalDetector, StrategyConfig
from trade_rules.wave_screening_v2 import infer_market, suggest_limit_price


def _align_topix(ohlcv: pd.DataFrame, topix: pd.DataFrame) -> pd.DataFrame:
    t = topix.copy()
    if not isinstance(t.index, pd.DatetimeIndex):
        t.index = pd.to_datetime(t.index)
    t = t.sort_index()
    t = t[~t.index.duplicated(keep="last")]
    tc = t["close"].reindex(ohlcv.index).ffill()
    return pd.DataFrame({"close": tc}, index=ohlcv.index)


def enrich_scan_result(ohlcv: pd.DataFrame, topix_ohlc_or_close: pd.DataFrame, *, ticker: str = "") -> dict:
    """
    直近バー基準のスナップショット（v2.0 定義書準拠）。
    trade_rules_candidate: スクリーニング通過かつ 4-1/4-2 エントリーパターンあり。
    """
    empty = {
        "trade_rules_candidate": False,
        "cleartrade_bonus": 0,
        "cleartrade_flags": {},
        "wave_v2_screen_pass": False,
        "wave_v2_entry_pattern": None,
        "wave_v2_limit_price": None,
    }
    if ohlcv is None or len(ohlcv) < 70:
        return empty

    df = ohlcv.copy()
    for c in ("open", "high", "low", "close", "volume"):
        if c not in df.columns:
            return {**empty, "cleartrade_flags": {"error": f"missing column {c}"}}

    if isinstance(topix_ohlc_or_close.columns, pd.MultiIndex):
        topix_ohlc_or_close.columns = [str(x[0]).lower() for x in topix_ohlc_or_close.columns]

    if "close" not in topix_ohlc_or_close.columns:
        topix_df = pd.DataFrame({"close": topix_ohlc_or_close.iloc[:, 0]})
    else:
        topix_df = topix_ohlc_or_close[["close"]].copy()

    topix_df.index = pd.to_datetime(topix_df.index).tz_localize(None)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    topix_aligned = _align_topix(df, topix_df)

    mkt = infer_market(ticker) if ticker else "JP"
    cfg = StrategyConfig(strategy_rules="v2", market=mkt)
    det = SignalDetector(cfg)
    df.attrs["ticker"] = ticker
    d = det.calculate_indicators(df, topix_aligned, market=mkt)
    sigs = det.detect_signals(d, market=mkt)

    last = d.index[-1]
    fired = any(s.get("trigger_date") == last for s in sigs)
    row = d.iloc[-1]

    bonus = 0
    flags: dict = {}
    screen = bool(row.get("screen_pass", False))
    flags["wave_v2_screen_pass"] = screen

    if screen:
        bonus += 15
    if bool(row.get("perfect_order", False)):
        bonus += 10
        flags["perfect_order"] = True
    if not pd.isna(row.get("rsi14")):
        rsi = float(row["rsi14"])
        flags["rsi14"] = round(rsi, 1)
        if 40 <= rsi <= 75:
            bonus += 8
    if not pd.isna(row.get("sma20_dev")):
        dev = float(row["sma20_dev"])
        flags["sma20_dev_pct"] = round(dev * 100, 2)
        if dev < 0.05:
            bonus += 10

    entry_pat = None
    limit_px = None
    if fired and sigs:
        last_sig = next(s for s in sigs if s.get("trigger_date") == last)
        entry_pat = last_sig.get("entry_pattern")
        limit_px = last_sig.get("limit_price")
    elif screen:
        from trade_rules.wave_screening_v2 import detect_entry_pattern

        i = len(d) - 1
        ent = detect_entry_pattern(d, i, cfg)
        if ent:
            entry_pat, limit_px = ent[0], ent[1]
        else:
            limit_px = suggest_limit_price(row, "snapshot")

    if entry_pat:
        flags["entry_pattern"] = entry_pat
        bonus += 12

    return {
        "trade_rules_candidate": fired or (screen and entry_pat is not None),
        "cleartrade_bonus": int(bonus),
        "cleartrade_flags": flags,
        "wave_v2_screen_pass": screen,
        "wave_v2_entry_pattern": entry_pat,
        "wave_v2_limit_price": round(limit_px, 2) if limit_px else None,
    }


def eligible_for_trading(rank: str, trade_rules_candidate: bool) -> bool:
    return rank in ("S", "A") and bool(trade_rules_candidate)
