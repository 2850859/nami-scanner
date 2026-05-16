"""
波乗りトレード スクリーニング条件定義書 v2.0 の実装。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from trade_rules.backtest_engine import StrategyConfig


def infer_market(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith(".T") or t.endswith(".TSE"):
        return "JP"
    return "US"


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def turnover_30d(df: pd.DataFrame, lookback: int = 30) -> pd.Series:
    return (df["close"] * df["volume"]).rolling(lookback).mean()


def add_v2_indicators(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    index_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    d = df.copy()
    d["sma5"] = d["close"].rolling(5).mean()
    d["sma10"] = d["close"].rolling(10).mean()
    d["sma20"] = d["close"].rolling(cfg.trend_sma).mean()
    d["sma60"] = d["close"].rolling(cfg.sma_long).mean()
    d["perfect_order"] = (d["sma5"] > d["sma10"]) & (d["sma10"] > d["sma20"])
    d["rsi14"] = rsi_wilder(d["close"], cfg.rsi_period)
    d["sma20_dev"] = d["close"] / d["sma20"] - 1.0
    d["turnover30"] = turnover_30d(d, cfg.turnover_lookback)
    d["recent_low_5d"] = d["low"].rolling(5).min()

    d["scr_v2_trend"] = (
        d["perfect_order"]
        & (d["sma20"] > d["sma60"])
        & (d["close"] > d["sma60"])
    )
    rsi_ok = (d["rsi14"] >= cfg.rsi_min) & (d["rsi14"] <= cfg.rsi_max)
    dev_ok = d["sma20_dev"] < cfg.sma20_dev_max
    hot_exclude = (d["rsi14"] >= cfg.rsi_hot_min) & (d["rsi14"] <= cfg.rsi_max) & (
        d["sma20_dev"] > cfg.sma20_dev_hot
    )
    d["scr_v2_heat"] = rsi_ok & dev_ok & ~hot_exclude

    market = cfg.market or "JP"
    min_turn = cfg.min_turnover_jpy if market == "JP" else cfg.min_turnover_usd
    d["scr_v2_liquidity"] = d["turnover30"] >= min_turn

    # 市場指数フィルタ: 指数終値 > 指数SMA20（JP=TOPIX, US=SPY）
    if index_df is not None and "close" in index_df.columns:
        idx_close = index_df["close"].reindex(d.index, method="ffill")
        idx_sma20 = idx_close.rolling(20).mean()
        d["index_close"] = idx_close
        d["index_sma20"] = idx_sma20
        d["scr_v2_index"] = idx_close > idx_sma20
    else:
        d["scr_v2_index"] = True

    d["screen_pass"] = (
        d["scr_v2_trend"] & d["scr_v2_heat"] & d["scr_v2_liquidity"] & d["scr_v2_index"]
    )
    return d


def entry_pattern_41(df: pd.DataFrame, i: int, cfg: StrategyConfig) -> bool:
    """4-1: SMA5下抜け後の再上抜け、または SMA10±1%タッチ陽線"""
    if i < 2:
        return False
    row = df.iloc[i]
    prev = df.iloc[i - 1]
    sma5, sma10 = row["sma5"], row["sma10"]
    if pd.isna(sma5) or pd.isna(sma10):
        return False

    reclaim = False
    for k in range(1, min(4, i + 1)):
        past = df.iloc[i - k]
        if pd.isna(past["sma5"]):
            continue
        if past["close"] < past["sma5"] and row["close"] > sma5:
            reclaim = True
            break

    band = cfg.entry_ma10_touch_band
    touch_bounce = (
        sma10 > 0
        and (abs(row["close"] / sma10 - 1.0) <= band)
        and row["close"] > row["open"]
        and row["close"] >= prev["close"]
    )
    return reclaim or touch_bounce


def entry_pattern_42(df: pd.DataFrame, i: int, cfg: StrategyConfig) -> bool:
    """4-2: SMA5上・乖離+2%以内・直前2〜3日が調整"""
    row = df.iloc[i]
    sma5 = row["sma5"]
    if pd.isna(sma5) or sma5 <= 0:
        return False
    if row["close"] <= sma5:
        return False
    if (row["close"] - sma5) / sma5 > cfg.entry_shallow_max_dist_sma5:
        return False
    n = cfg.entry_adjust_lookback
    if i < n:
        return False
    adjust_days = 0
    for k in range(1, n + 1):
        p = df.iloc[i - k]
        bearish = p["close"] < p["open"]
        small_body = abs(p["close"] - p["open"]) / max(p["open"], 1e-9) < 0.01
        if bearish or small_body:
            adjust_days += 1
    return adjust_days >= max(2, n - 1)


def suggest_limit_price(row: pd.Series, pattern: str) -> float:
    """4-3: SMA5 / SMA10 / 直近安値を目安に指値"""
    candidates = [float(row["close"])]
    for col in ("sma5", "sma10", "recent_low_5d"):
        v = row.get(col)
        if v is not None and not pd.isna(v) and float(v) > 0:
            candidates.append(float(v))
    return min(candidates)


def v2_signal_score(row: pd.Series, dev_max: float = 0.07) -> float:
    """乖離率が小さいほど高スコア（押し目が深い順の代理）"""
    dev = float(row["sma20_dev"]) if not pd.isna(row.get("sma20_dev")) else dev_max
    return max(0.0, dev_max - dev)


def detect_entry_pattern(
    df: pd.DataFrame, i: int, cfg: StrategyConfig
) -> Optional[tuple[str, float]]:
    if entry_pattern_41(df, i, cfg):
        row = df.iloc[i]
        return "4-1", suggest_limit_price(row, "4-1")
    if entry_pattern_42(df, i, cfg):
        row = df.iloc[i]
        return "4-2", suggest_limit_price(row, "4-2")
    return None


def resolve_limit_fill(
    df: pd.DataFrame,
    trigger_i: int,
    limit_price: float,
    max_wait_days: int = 3,
) -> Optional[tuple[pd.Timestamp, float]]:
    """指値: 翌営業日以降、安値が指値以下なら指値で約定"""
    for j in range(trigger_i + 1, min(trigger_i + 1 + max_wait_days, len(df))):
        row = df.iloc[j]
        if float(row["low"]) <= limit_price:
            return df.index[j], limit_price
    return None
