"""
波乗り × cleartrade 統合トレードシステム
バックテストエンジン (本番用)

依存: pandas, numpy, requests（J-Quants利用時）
ローカル検証: python -m trade_rules.run_cleartrade_yfinance
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

import numpy as np
import pandas as pd

EntryMode = Literal["next_open", "close", "next_vwap"]
StrategyRules = Literal["v2", "cleartrade"]


# ============================================================
# 設定
# ============================================================


@dataclass
class StrategyConfig:
    """戦略パラメータ"""

    strategy_rules: StrategyRules = "v2"
    market: Optional[str] = None  # JP / US（未設定時はティッカーから推定）

    # --- v2.0 スクリーニング ---
    sma_long: int = 60
    rsi_period: int = 14
    rsi_min: float = 40.0
    rsi_max: float = 75.0
    rsi_hot_min: float = 65.0
    sma20_dev_max: float = 0.07
    sma20_dev_hot: float = 0.05
    turnover_lookback: int = 30
    min_turnover_jpy: float = 5e9
    min_turnover_usd: float = 5e8
    min_market_cap_jp: float = 2e12
    min_market_cap_us: float = 200e9

    # --- v2.0 エントリー ---
    entry_shallow_max_dist_sma5: float = 0.02
    entry_ma10_touch_band: float = 0.01
    entry_adjust_lookback: int = 3
    limit_wait_days: int = 3
    stop_sma20_break_pct: float = 0.01
    trail_exit_sma: int = 10
    breakeven_trigger_pct: float = 0.10
    rsi_overbought: float = 80.0
    position_allocation_pct: float = 0.125
    max_sector_allocation_pct: float = 0.30

    # --- US株専用オーバーライド（None のとき汎用値を使用）---
    stop_loss_pct_us: float = 0.05       # JP 7% → US 5%（損失を小さく）
    max_holding_days_us: int = 20        # JP 15日 → US 20日（利益を伸ばす）
    rsi_overbought_us: float = 75.0      # JP 80 → US 75（早めに半利確）
    sma20_dev_max_us: float = 0.10       # JP 7% → US 10%（自然乖離が大きい）

    # --- cleartrade（legacy）---
    volume_multiplier: float = 2.0
    breakout_lookback: int = 20
    momentum_period: int = 20
    momentum_threshold: float = 0.05
    trend_sma: int = 20
    perfect_order_ma_mid: int = 10
    require_perfect_order: bool = True

    dip_lookback: int = 10
    # 固定%押し目（use_atr_pullback=False のとき）
    dip_min: float = -0.05
    dip_max: float = -0.03

    use_atr_pullback: bool = True
    atr_period: int = 14
    atr_pullback_min_mult: float = 1.0
    atr_pullback_max_mult: float = 1.5

    volume_contraction: float = 0.7
    peak_lookback: int = 20

    stop_loss_pct: float = 0.07
    tp1_level: float = 0.10
    tp1_ratio: float = 0.5
    trail_sma: int = 5
    max_holding_days: int = 15

    volume_reexpand_ratio: float = 1.20
    require_volume_reexpand: bool = True

    entry_mode: EntryMode = "next_open"

    risk_per_trade: float = 0.002
    max_positions: int = 6
    replacement_threshold: float = 1.2

    earnings_blackout_days: int = 3
    gap_up_threshold: float = 0.05

    slippage: float = 0.001
    commission: float = 0.0005

    min_market_cap: float = 3e11
    max_market_cap: float = 3e12
    min_avg_turnover: float = 5e9

    screen_recent_days: int = 20
    use_strict_peak_day: bool = False

    sector_filter_enabled: bool = False


def _atr_wilder(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(
        axis=1
    )
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ============================================================
# データ取得 (J-Quants API)
# ============================================================


class JQuantsClient:
    """J-Quants APIクライアント (簡易版)"""

    def __init__(self, mail: str, password: str):
        self.mail = mail
        self.password = password
        self.id_token = None
        self.refresh_token = None
        self._authenticate()

    def _authenticate(self):
        import requests

        resp = requests.post(
            "https://api.jquants.com/v1/token/auth_user",
            json={"mailaddress": self.mail, "password": self.password},
        )
        resp.raise_for_status()
        self.refresh_token = resp.json()["refreshToken"]
        resp = requests.post(
            f"https://api.jquants.com/v1/token/auth_refresh?refreshtoken={self.refresh_token}"
        )
        resp.raise_for_status()
        self.id_token = resp.json()["idToken"]

    def get_listed_info(self) -> pd.DataFrame:
        import requests

        resp = requests.get(
            "https://api.jquants.com/v1/listed/info",
            headers={"Authorization": f"Bearer {self.id_token}"},
        )
        resp.raise_for_status()
        return pd.DataFrame(resp.json()["info"])

    def get_daily_quotes(self, code: str, from_date: str, to_date: str) -> pd.DataFrame:
        import requests

        resp = requests.get(
            "https://api.jquants.com/v1/prices/daily_quotes",
            headers={"Authorization": f"Bearer {self.id_token}"},
            params={"code": code, "from": from_date, "to": to_date},
        )
        resp.raise_for_status()
        df = pd.DataFrame(resp.json()["daily_quotes"])
        if df.empty:
            return df
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            adj_col = f"Adjustment{col}"
            if adj_col in df.columns:
                df[col.lower()] = df[adj_col]
            else:
                df[col.lower()] = df[col]
        return df[["open", "high", "low", "close", "volume"]]

    def get_topix(self, from_date: str, to_date: str) -> pd.DataFrame:
        import requests

        resp = requests.get(
            "https://api.jquants.com/v1/indices/topix",
            headers={"Authorization": f"Bearer {self.id_token}"},
            params={"from": from_date, "to": to_date},
        )
        resp.raise_for_status()
        df = pd.DataFrame(resp.json()["topix"])
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        df["close"] = df["Close"]
        return df[["close"]]


# ============================================================
# シグナル検出
# ============================================================


class SignalDetector:
    def __init__(self, config: StrategyConfig):
        self.cfg = config

    def calculate_indicators(
        self,
        df: pd.DataFrame,
        topix: pd.DataFrame,
        *,
        market: Optional[str] = None,
    ) -> pd.DataFrame:
        cfg = self.cfg
        if cfg.strategy_rules == "v2":
            from trade_rules.wave_screening_v2 import add_v2_indicators, infer_market

            mkt = market or cfg.market or infer_market(
                str(df.attrs.get("ticker", "")) if df.attrs.get("ticker") else "JP"
            )
            cfg.market = mkt
            index_df = topix if topix is not None and not topix.empty else None
            return add_v2_indicators(df, cfg, index_df=index_df)

        d = df.copy()

        d["sma20"] = d["close"].rolling(cfg.trend_sma).mean()
        d["sma10"] = d["close"].rolling(cfg.perfect_order_ma_mid).mean()
        d["sma5"] = d["close"].rolling(cfg.trail_sma).mean()
        d["perfect_order"] = (d["sma5"] > d["sma10"]) & (d["sma10"] > d["sma20"])
        d["vol_sma20"] = d["volume"].rolling(20).mean()
        d["vol_sma5"] = d["volume"].rolling(5).mean()

        d["high20"] = d["high"].rolling(cfg.breakout_lookback).max()
        d["high10"] = d["high"].rolling(cfg.dip_lookback).max()
        d["return20"] = d["close"].pct_change(cfg.momentum_period)
        d["atr14"] = _atr_wilder(d, cfg.atr_period)

        topix_aligned = topix.reindex(d.index, method="ffill")
        d["topix_close"] = topix_aligned["close"]
        d["topix_sma20"] = d["topix_close"].rolling(cfg.trend_sma).mean()

        d["peak_volume"] = (
            self._find_peak_volume_strict(d, cfg.peak_lookback)
            if cfg.use_strict_peak_day
            else self._find_peak_volume_at_high(d, cfg.peak_lookback)
        )

        d["gap"] = d["open"] / d["close"].shift(1) - 1
        d["vol_yesterday"] = d["volume"].shift(1)
        d["volume_reexpand"] = d["volume"] >= d["vol_yesterday"] * cfg.volume_reexpand_ratio

        d["scr_S1"] = d["volume"] / d["vol_sma20"] >= cfg.volume_multiplier
        d["scr_S2"] = d["close"] >= d["high20"]
        d["scr_S3"] = d["return20"] >= cfg.momentum_threshold
        d["scr_T1"] = d["close"] > d["sma20"]
        d["scr_T2"] = d["topix_close"] > d["topix_sma20"]
        d["scr_T3"] = d["perfect_order"]
        screen_parts = [d["scr_S1"], d["scr_S2"], d["scr_S3"], d["scr_T1"], d["scr_T2"]]
        if cfg.require_perfect_order:
            screen_parts.append(d["scr_T3"])
        d["screen_pass"] = screen_parts[0]
        for part in screen_parts[1:]:
            d["screen_pass"] = d["screen_pass"] & part
        sr = (
            d["screen_pass"]
            .shift(1)
            .rolling(cfg.screen_recent_days, min_periods=1)
            .max()
        )
        d["screen_recent"] = sr.fillna(0).astype(bool)

        return d

    def _find_peak_volume_strict(self, df: pd.DataFrame, period: int) -> pd.Series:
        result = pd.Series(np.nan, index=df.index)
        vol = df["volume"].values
        high = df["high"].values
        for i in range(period - 1, len(df)):
            window_vol = vol[i - period + 1 : i + 1]
            window_high = high[i - period + 1 : i + 1]
            max_vol_idx = int(np.argmax(window_vol))
            max_high_idx = int(np.argmax(window_high))
            if max_vol_idx == max_high_idx:
                result.iloc[i] = window_vol[max_vol_idx]
        return result

    def _find_peak_volume_at_high(self, df: pd.DataFrame, period: int) -> pd.Series:
        result = pd.Series(np.nan, index=df.index)
        vol = df["volume"].values
        high = df["high"].values
        for i in range(period - 1, len(df)):
            wh = high[i - period + 1 : i + 1]
            wv = vol[i - period + 1 : i + 1]
            mh = np.max(wh)
            rel = np.where(wh == mh)[0][-1]
            result.iloc[i] = wv[rel]
        return result

    def _pullback_low_at(self, df: pd.DataFrame, i: int, lookback: int) -> float:
        lo = df["low"].iloc[max(0, i - lookback + 1) : i + 1]
        return float(lo.min())

    def _dip_ok(self, row, cfg: StrategyConfig) -> bool:
        if cfg.use_atr_pullback:
            atr = row["atr14"]
            if pd.isna(atr) or atr <= 0:
                return False
            depth = row["high10"] - row["close"]
            lo_b = cfg.atr_pullback_min_mult * atr
            hi_b = cfg.atr_pullback_max_mult * atr
            return lo_b <= depth <= hi_b
        dip_pct = row["close"] / row["high10"] - 1
        return cfg.dip_min <= dip_pct <= cfg.dip_max

    def _signal_score(self, row, cfg: StrategyConfig, dip_pct: float, vol_ratio: float) -> float:
        if cfg.use_atr_pullback and not pd.isna(row.get("atr14")) and row["atr14"] > 0:
            depth = row["high10"] - row["close"]
            mid = (cfg.atr_pullback_min_mult + cfg.atr_pullback_max_mult) / 2.0 * row["atr14"]
            span = (cfg.atr_pullback_max_mult - cfg.atr_pullback_min_mult) / 2.0 * row["atr14"]
            span = max(span, row["atr14"] * 0.05)
            dip_term = max(0.0, 1.0 - abs(depth - mid) / span)
        else:
            dip_term = max(0.0, 1.0 - abs(dip_pct + 0.04) / 0.01)
        return (
            0.4 * (vol_ratio - 2.0)
            + 0.3 * (row["return20"] - 0.05) * 10
            + 0.3 * dip_term
        )

    def _resolve_entry(
        self, df: pd.DataFrame, i: int, cfg: StrategyConfig
    ) -> Optional[tuple]:
        mode = cfg.entry_mode
        slip = 1.0 + cfg.slippage
        if mode == "next_open":
            if i + 1 >= len(df):
                return None
            ed = df.index[i + 1]
            px = float(df.iloc[i + 1]["open"] * slip)
            return ed, px
        if mode == "close":
            ed = df.index[i]
            px = float(df.iloc[i]["close"] * slip)
            return ed, px
        if mode == "next_vwap":
            if i + 1 >= len(df):
                return None
            row = df.iloc[i + 1]
            ed = df.index[i + 1]
            if "vwap" in df.columns and pd.notna(row.get("vwap", np.nan)):
                base = float(row["vwap"])
            else:
                base = float(row["high"] + row["low"] + row["close"]) / 3.0
            px = base * slip
            return ed, px
        return None

    def detect_signals(
        self,
        df: pd.DataFrame,
        sector_ok: Optional[pd.Series] = None,
        *,
        market: Optional[str] = None,
    ) -> List[Dict]:
        cfg = self.cfg
        if cfg.strategy_rules == "v2":
            return self._detect_signals_v2(df, market=market)

        signals: List[Dict] = []

        if sector_ok is not None:
            sector_aligned = sector_ok.reindex(df.index)
        else:
            sector_aligned = None

        for i in range(1, len(df) - 1):
            row = df.iloc[i]
            if pd.isna(row["sma20"]) or pd.isna(row["high20"]) or pd.isna(row["topix_sma20"]):
                continue
            if cfg.require_perfect_order and (
                pd.isna(row["sma10"]) or not bool(row["perfect_order"])
            ):
                continue
            if not bool(row["screen_recent"]):
                continue

            if sector_aligned is not None:
                sv = sector_aligned.iloc[i]
                if pd.isna(sv) or not bool(sv):
                    continue

            T1 = row["close"] > row["sma20"]
            T2 = row["topix_close"] > row["topix_sma20"]
            T3 = bool(row["perfect_order"]) if cfg.require_perfect_order else True

            P1 = self._dip_ok(row, cfg)
            P2 = (not pd.isna(row["peak_volume"])) and (
                row["vol_sma5"] < cfg.volume_contraction * row["peak_volume"]
            )
            P3 = row["close"] >= row["sma20"]

            prev = df.iloc[i - 1]
            E1 = row["close"] > prev["high"]
            E2 = row["open"] < prev["close"] and row["close"] > prev["open"] and row["close"] > row["open"]
            vy = row["vol_yesterday"]
            if cfg.require_volume_reexpand:
                vol_ok = (
                    pd.notna(vy)
                    and float(vy) > 0
                    and float(row["volume"]) >= float(vy) * cfg.volume_reexpand_ratio
                )
            else:
                vol_ok = True

            gap_exclude = row["gap"] >= cfg.gap_up_threshold
            neg_vol_exclude = row["close"] < row["open"] and row["volume"] > row["vol_sma20"]

            if not all(
                [T1, T2, T3, P1, P2, P3, (E1 or E2), vol_ok, not gap_exclude, not neg_vol_exclude]
            ):
                continue

            resolved = self._resolve_entry(df, i, cfg)
            if resolved is None:
                continue
            entry_date, entry_price = resolved
            dip_pct = row["close"] / row["high10"] - 1
            vol_ratio = row["volume"] / row["vol_sma20"]
            pullback_low = self._pullback_low_at(df, i, cfg.dip_lookback)
            score = self._signal_score(row, cfg, dip_pct, vol_ratio)

            signals.append(
                {
                    "trigger_date": df.index[i],
                    "date": df.index[i],
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "pullback_low": pullback_low,
                    "signal_score": score,
                    "vol_ratio": vol_ratio,
                    "return20": row["return20"],
                    "dip_pct": dip_pct,
                    "trigger": "breakout" if E1 else "engulfing",
                    "entry_mode": cfg.entry_mode,
                }
            )
        return signals

    def _detect_signals_v2(
        self,
        df: pd.DataFrame,
        *,
        market: Optional[str] = None,
    ) -> List[Dict]:
        from trade_rules.wave_screening_v2 import (
            detect_entry_pattern,
            suggest_limit_price,
            v2_signal_score,
        )

        cfg = self.cfg
        mkt = market or cfg.market or "JP"
        cfg.market = mkt
        signals: List[Dict] = []
        start = max(cfg.sma_long + 2, cfg.turnover_lookback + 2)
        slip = 1.0 + cfg.slippage

        for i in range(start, len(df) - 1):
            row = df.iloc[i]
            if pd.isna(row.get("sma60")) or not bool(row.get("screen_pass", False)):
                continue

            entry = detect_entry_pattern(df, i, cfg)
            if entry is None:
                continue
            pattern, limit_px = entry

            # 翌営業日寄付成行（スリッページ込み）
            next_row = df.iloc[i + 1]
            entry_date = df.index[i + 1]
            entry_price = float(next_row["open"]) * slip

            signals.append(
                {
                    "trigger_date": df.index[i],
                    "date": df.index[i],
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "limit_price": limit_px,  # 参考値として保持
                    "pullback_low": float(row.get("recent_low_5d", row["low"])),
                    "signal_score": v2_signal_score(row, cfg.sma20_dev_max),
                    "sma20_dev": float(row["sma20_dev"]),
                    "rsi14": float(row["rsi14"]),
                    "trigger": pattern,
                    "entry_pattern": pattern,
                    "entry_mode": "next_open",
                }
            )
        return signals


# ============================================================
# バックテスター
# ============================================================


@dataclass
class Position:
    code: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    signal_score: float
    pullback_low: float
    market: str = "JP"
    tp1_done: bool = False
    breakeven_active: bool = False
    half_taken_rsi: bool = False


@dataclass
class Trade:
    code: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    exit_reason: str
    pnl: float
    pnl_pct: float
    holding_days: int = 0
    trade_group: str = ""
    assumed_slippage_pct: float = 0.0


class Backtester:
    def __init__(self, config: StrategyConfig, initial_capital: float = 1e8):
        self.cfg = config
        self.initial_capital = initial_capital

    def _holding_days(self, df: pd.DataFrame, entry_date: pd.Timestamp, current_date: pd.Timestamp) -> int:
        try:
            ei = df.index.get_loc(entry_date)
            ci = df.index.get_loc(current_date)
            if isinstance(ei, slice) or isinstance(ci, slice):
                return 0
            return int(ci - ei)
        except Exception:
            return 0

    def _record_exit(
        self,
        *,
        code: str,
        pos: Position,
        exit_date: pd.Timestamp,
        exit_price: float,
        shares: int,
        reason: str,
        hd: int,
        trades: List[Trade],
        capital: float,
        cfg: StrategyConfig,
    ) -> float:
        pnl = (exit_price - pos.entry_price) * shares - (
            exit_price + pos.entry_price
        ) * shares * cfg.commission
        tg = f"{code}:{pos.entry_date.date()}"
        trades.append(
            Trade(
                code=code,
                entry_date=pos.entry_date,
                exit_date=exit_date,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                shares=shares,
                exit_reason=reason,
                pnl=pnl,
                pnl_pct=exit_price / pos.entry_price - 1,
                holding_days=hd,
                trade_group=tg,
                assumed_slippage_pct=cfg.slippage * 100,
            )
        )
        return capital + exit_price * shares

    def _exit_position_v2(
        self,
        cfg: StrategyConfig,
        code: str,
        pos: Position,
        row: pd.Series,
        df: pd.DataFrame,
        idx: int,
        next_open: float,
        hd: int,
        trades: List[Trade],
        capital: float,
    ) -> tuple[bool, float]:
        exit_date = df.index[idx + 1]
        sma10 = row.get("sma10")
        sma20 = row.get("sma20")
        rsi = row.get("rsi14")

        if not pd.isna(row.get("sma5")) and not pd.isna(row.get("sma10")):
            if float(row["sma5"]) < float(row["sma10"]):
                capital = self._record_exit(
                    code=code,
                    pos=pos,
                    exit_date=exit_date,
                    exit_price=next_open,
                    shares=pos.shares,
                    reason="po_break",
                    hd=hd,
                    trades=trades,
                    capital=capital,
                    cfg=cfg,
                )
                return True, capital

        _sl = cfg.stop_loss_pct_us if pos.market == "US" else cfg.stop_loss_pct
        if row["close"] <= pos.entry_price * (1 - _sl):
            capital = self._record_exit(
                code=code,
                pos=pos,
                exit_date=exit_date,
                exit_price=next_open,
                shares=pos.shares,
                reason="stop_loss_pct",
                hd=hd,
                trades=trades,
                capital=capital,
                cfg=cfg,
            )
            return True, capital

        if not pd.isna(sma20) and float(row["close"]) < float(sma20) * (
            1 - cfg.stop_sma20_break_pct
        ):
            capital = self._record_exit(
                code=code,
                pos=pos,
                exit_date=exit_date,
                exit_price=next_open,
                shares=pos.shares,
                reason="stop_sma20_break",
                hd=hd,
                trades=trades,
                capital=capital,
                cfg=cfg,
            )
            return True, capital

        if not pos.breakeven_active and row["high"] >= pos.entry_price * (
            1 + cfg.breakeven_trigger_pct
        ):
            pos.breakeven_active = True

        _rsi_ob = cfg.rsi_overbought_us if pos.market == "US" else cfg.rsi_overbought
        if not pd.isna(rsi) and float(rsi) > _rsi_ob and not pos.half_taken_rsi:
            half = pos.shares // 2
            if half > 0:
                capital = self._record_exit(
                    code=code,
                    pos=pos,
                    exit_date=exit_date,
                    exit_price=next_open,
                    shares=half,
                    reason="rsi_half",
                    hd=hd,
                    trades=trades,
                    capital=capital,
                    cfg=cfg,
                )
                pos.shares -= half
                pos.half_taken_rsi = True

        if pos.breakeven_active:
            if row["close"] < pos.entry_price:
                capital = self._record_exit(
                    code=code,
                    pos=pos,
                    exit_date=exit_date,
                    exit_price=next_open,
                    shares=pos.shares,
                    reason="breakeven_stop",
                    hd=hd,
                    trades=trades,
                    capital=capital,
                    cfg=cfg,
                )
                return True, capital
            if not pd.isna(sma10) and row["close"] < sma10:
                capital = self._record_exit(
                    code=code,
                    pos=pos,
                    exit_date=exit_date,
                    exit_price=next_open,
                    shares=pos.shares,
                    reason="trail_sma10",
                    hd=hd,
                    trades=trades,
                    capital=capital,
                    cfg=cfg,
                )
                return True, capital

        _max_hd = cfg.max_holding_days_us if pos.market == "US" else cfg.max_holding_days
        if hd >= _max_hd:
            capital = self._record_exit(
                code=code,
                pos=pos,
                exit_date=exit_date,
                exit_price=next_open,
                shares=pos.shares,
                reason="max_holding_days",
                hd=hd,
                trades=trades,
                capital=capital,
                cfg=cfg,
            )
            return True, capital

        return False, capital

    def run(
        self,
        all_data: Dict[str, pd.DataFrame],
        topix: pd.DataFrame,
        sector_gates: Optional[Dict[str, pd.Series]] = None,
        *,
        us_index: Optional[pd.DataFrame] = None,
    ) -> Dict:
        cfg = self.cfg
        detector = SignalDetector(cfg)

        from trade_rules.wave_screening_v2 import infer_market

        enriched: Dict[str, pd.DataFrame] = {}
        all_signals: List[Dict] = []
        for code, df in all_data.items():
            mkt = infer_market(code)
            df_run = df.copy()
            df_run.attrs["ticker"] = code
            idx_df = us_index if (mkt == "US" and us_index is not None) else topix
            d = detector.calculate_indicators(df_run, idx_df, market=mkt)
            enriched[code] = d
            sg = sector_gates.get(code) if sector_gates else None
            if cfg.sector_filter_enabled and sg is None:
                continue
            for sig in detector.detect_signals(d, sector_ok=sg, market=mkt):
                sig["code"] = code
                all_signals.append(sig)

        all_signals.sort(key=lambda s: s["date"])

        all_dates = sorted(set(d for df in enriched.values() for d in df.index))

        capital = self.initial_capital
        positions: Dict[str, Position] = {}
        trades: List[Trade] = []
        equity_curve: List[Dict] = []

        for current_date in all_dates:
            to_close: List[str] = []

            for code, pos in positions.items():
                if code not in enriched or current_date not in enriched[code].index:
                    continue
                df = enriched[code]
                if current_date <= pos.entry_date:
                    continue
                row = df.loc[current_date]
                idx = df.index.get_loc(current_date)
                if idx + 1 >= len(df):
                    continue
                next_open = float(df.iloc[idx + 1]["open"] * (1 - cfg.slippage))
                hd = self._holding_days(df, pos.entry_date, current_date)

                if cfg.strategy_rules == "v2":
                    closed, capital = self._exit_position_v2(
                        cfg, code, pos, row, df, idx, next_open, hd, trades, capital
                    )
                    if closed:
                        to_close.append(code)
                    continue

                _sl_ct = cfg.stop_loss_pct_us if pos.market == "US" else cfg.stop_loss_pct
                stop1 = row["close"] <= pos.entry_price * (1 - _sl_ct)
                stop2 = row["close"] < pos.pullback_low
                if stop1 or stop2:
                    reason = "stop_loss_pct" if stop1 else "stop_loss_pullback_low"
                    pnl = (next_open - pos.entry_price) * pos.shares - (
                        next_open + pos.entry_price
                    ) * pos.shares * cfg.commission
                    capital += next_open * pos.shares
                    tg = f"{code}:{pos.entry_date.date()}"
                    trades.append(
                        Trade(
                            code=code,
                            entry_date=pos.entry_date,
                            exit_date=df.index[idx + 1],
                            entry_price=pos.entry_price,
                            exit_price=next_open,
                            shares=pos.shares,
                            exit_reason=reason,
                            pnl=pnl,
                            pnl_pct=next_open / pos.entry_price - 1,
                            holding_days=hd,
                            trade_group=tg,
                            assumed_slippage_pct=cfg.slippage * 100,
                        )
                    )
                    to_close.append(code)
                    continue

                _max_hd_ct = cfg.max_holding_days_us if pos.market == "US" else cfg.max_holding_days
                if hd >= _max_hd_ct:
                    pnl = (next_open - pos.entry_price) * pos.shares - (
                        next_open + pos.entry_price
                    ) * pos.shares * cfg.commission
                    capital += next_open * pos.shares
                    tg = f"{code}:{pos.entry_date.date()}"
                    trades.append(
                        Trade(
                            code=code,
                            entry_date=pos.entry_date,
                            exit_date=df.index[idx + 1],
                            entry_price=pos.entry_price,
                            exit_price=next_open,
                            shares=pos.shares,
                            exit_reason="max_holding_days",
                            pnl=pnl,
                            pnl_pct=next_open / pos.entry_price - 1,
                            holding_days=hd,
                            trade_group=tg,
                            assumed_slippage_pct=cfg.slippage * 100,
                        )
                    )
                    to_close.append(code)
                    continue

                if not pos.tp1_done and row["high"] >= pos.entry_price * (1 + cfg.tp1_level):
                    half = pos.shares // 2
                    if half > 0:
                        pnl = (next_open - pos.entry_price) * half - (
                            next_open + pos.entry_price
                        ) * half * cfg.commission
                        capital += next_open * half
                        tg = f"{code}:{pos.entry_date.date()}"
                        trades.append(
                            Trade(
                                code=code,
                                entry_date=pos.entry_date,
                                exit_date=df.index[idx + 1],
                                entry_price=pos.entry_price,
                                exit_price=next_open,
                                shares=half,
                                exit_reason="tp1_partial",
                                pnl=pnl,
                                pnl_pct=next_open / pos.entry_price - 1,
                                holding_days=hd,
                                trade_group=tg,
                                assumed_slippage_pct=cfg.slippage * 100,
                            )
                        )
                        pos.shares -= half
                        pos.tp1_done = True
                    continue

                if pos.tp1_done:
                    sma5 = row["sma5"]
                    if not pd.isna(sma5) and row["close"] < sma5:
                        pnl = (next_open - pos.entry_price) * pos.shares - (
                            next_open + pos.entry_price
                        ) * pos.shares * cfg.commission
                        capital += next_open * pos.shares
                        tg = f"{code}:{pos.entry_date.date()}"
                        trades.append(
                            Trade(
                                code=code,
                                entry_date=pos.entry_date,
                                exit_date=df.index[idx + 1],
                                entry_price=pos.entry_price,
                                exit_price=next_open,
                                shares=pos.shares,
                                exit_reason="trail_ma5",
                                pnl=pnl,
                                pnl_pct=next_open / pos.entry_price - 1,
                                holding_days=hd,
                                trade_group=tg,
                                assumed_slippage_pct=cfg.slippage * 100,
                            )
                        )
                        to_close.append(code)

            for code in to_close:
                del positions[code]

            today_signals = [
                s
                for s in all_signals
                if s["entry_date"] == current_date and s["code"] not in positions
            ]
            today_signals.sort(key=lambda s: s["signal_score"], reverse=True)

            for sig in today_signals:
                total_equity = capital
                for c, pos in positions.items():
                    if current_date in enriched[c].index:
                        total_equity += enriched[c].loc[current_date, "close"] * pos.shares

                if cfg.strategy_rules == "v2":
                    shares = int(
                        total_equity * cfg.position_allocation_pct / sig["entry_price"]
                    )
                else:
                    _sl_sz = cfg.stop_loss_pct_us if infer_market(sig["code"]) == "US" else cfg.stop_loss_pct
                    risk_amount = total_equity * cfg.risk_per_trade
                    shares = int(risk_amount / (sig["entry_price"] * _sl_sz))

                if shares <= 0:
                    continue

                cost = sig["entry_price"] * shares

                if len(positions) < cfg.max_positions:
                    if capital >= cost:
                        capital -= cost
                        positions[sig["code"]] = Position(
                            code=sig["code"],
                            entry_date=current_date,
                            entry_price=sig["entry_price"],
                            shares=shares,
                            signal_score=sig["signal_score"],
                            pullback_low=float(sig["pullback_low"]),
                            market=infer_market(sig["code"]),
                        )
                else:
                    weakest = min(positions.values(), key=lambda p: p.signal_score)
                    if sig["signal_score"] > weakest.signal_score * cfg.replacement_threshold:
                        df_w = enriched[weakest.code]
                        if current_date in df_w.index:
                            widx = df_w.index.get_loc(current_date)
                            if widx + 1 < len(df_w):
                                exit_price = float(
                                    df_w.iloc[widx + 1]["open"] * (1 - cfg.slippage)
                                )
                                pnl = (exit_price - weakest.entry_price) * weakest.shares
                                capital += exit_price * weakest.shares
                                hd = self._holding_days(
                                    df_w, weakest.entry_date, current_date
                                )
                                tg = f"{weakest.code}:{weakest.entry_date.date()}"
                                trades.append(
                                    Trade(
                                        code=weakest.code,
                                        entry_date=weakest.entry_date,
                                        exit_date=df_w.index[widx + 1],
                                        entry_price=weakest.entry_price,
                                        exit_price=exit_price,
                                        shares=weakest.shares,
                                        exit_reason="replaced",
                                        pnl=pnl,
                                        pnl_pct=exit_price / weakest.entry_price - 1,
                                        holding_days=hd,
                                        trade_group=tg,
                                        assumed_slippage_pct=cfg.slippage * 100,
                                    )
                                )
                                del positions[weakest.code]
                                if capital >= cost:
                                    capital -= cost
                                    positions[sig["code"]] = Position(
                                        code=sig["code"],
                                        entry_date=current_date,
                                        entry_price=sig["entry_price"],
                                        shares=shares,
                                        signal_score=sig["signal_score"],
                                        pullback_low=float(sig["pullback_low"]),
                                        market=infer_market(sig["code"]),
                                    )

            total_equity = capital
            for code, pos in positions.items():
                if current_date in enriched[code].index:
                    total_equity += enriched[code].loc[current_date, "close"] * pos.shares
            equity_curve.append({"date": current_date, "equity": total_equity})

        return {
            "trades": trades,
            "equity_curve": pd.DataFrame(equity_curve).set_index("date"),
            "final_capital": equity_curve[-1]["equity"] if equity_curve else self.initial_capital,
        }


# ============================================================
# 評価指標・CSV
# ============================================================


def calculate_metrics(result: Dict, initial_capital: float) -> Dict:
    trades: List[Trade] = result["trades"]
    equity = result["equity_curve"]

    if not trades:
        return {"error": "No trades executed"}

    pnls = np.array([t.pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    pnl_pcts = np.array([t.pnl_pct for t in trades])
    win_pct = pnl_pcts[pnls > 0]
    loss_pct = pnl_pcts[pnls <= 0]

    final = result["final_capital"]
    total_return = (final / initial_capital - 1) * 100
    days = (equity.index[-1] - equity.index[0]).days if len(equity) > 1 else 1
    years = max(days / 365.25, 1e-9)
    annual_return = (np.power(final / initial_capital, 1 / years) - 1) * 100

    running_max = equity["equity"].cummax()
    dd = (equity["equity"] - running_max) / running_max
    max_dd = abs(dd.min()) * 100

    daily_returns = equity["equity"].pct_change().dropna()
    sharpe = (
        (daily_returns.mean() / daily_returns.std() * np.sqrt(252))
        if daily_returns.std() > 0
        else 0
    )

    hold_days = [t.holding_days for t in trades]

    streak = 0
    max_loss_streak = 0
    for t in trades:
        if t.pnl <= 0:
            streak += 1
            max_loss_streak = max(max_loss_streak, streak)
        else:
            streak = 0

    avg_slip = float(np.mean([t.assumed_slippage_pct for t in trades]))

    return {
        "total_return_pct": total_return,
        "annual_return_pct": annual_return,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "trade_count": len(trades),
        "win_rate_pct": len(wins) / len(trades) * 100,
        "avg_win": float(wins.mean()) if len(wins) > 0 else 0.0,
        "avg_loss": float(abs(losses.mean())) if len(losses) > 0 else 0.0,
        "avg_win_pct": float(win_pct.mean()) * 100 if len(win_pct) > 0 else 0.0,
        "avg_loss_pct": float(abs(loss_pct.mean())) * 100 if len(loss_pct) > 0 else 0.0,
        "risk_reward": float(wins.mean() / abs(losses.mean()))
        if len(wins) > 0 and len(losses) > 0 and losses.mean() != 0
        else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum()))
        if len(losses) > 0 and losses.sum() != 0 and wins.sum() > 0
        else 0.0,
        "final_capital": final,
        "avg_holding_days": float(np.mean(hold_days)) if hold_days else 0.0,
        "max_consecutive_losses": max_loss_streak,
        "avg_assumed_slippage_pct": avg_slip,
    }


def trades_to_dataframe(trades: List[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    rows = []
    for t in trades:
        rows.append(
            {
                "code": t.code,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "shares": t.shares,
                "exit_reason": t.exit_reason,
                "pnl": t.pnl,
                "pnl_pct": t.pnl_pct * 100,
                "holding_days": t.holding_days,
                "trade_group": t.trade_group,
                "assumed_slippage_pct": t.assumed_slippage_pct,
            }
        )
    return pd.DataFrame(rows)


def export_backtest_reports(
    result: Dict,
    metrics: Dict,
    tickers_sectors: Optional[Dict[str, str]],
    out_dir: str,
    prefix: str = "cleartrade",
) -> Dict[str, str]:
    from pathlib import Path

    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, str] = {}

    trades = result["trades"]
    tdf = trades_to_dataframe(trades)

    if not tdf.empty:
        tc = tdf.copy()
        tc["month"] = pd.to_datetime(tc["exit_date"]).dt.to_period("M").astype(str)
        monthly = tc.groupby("month").agg(pnl=("pnl", "sum"), trades=("pnl", "count"))
        mpath = p / f"{prefix}_monthly.csv"
        monthly.to_csv(mpath, encoding="utf-8-sig")
        paths["monthly"] = str(mpath)

        by_sym = tc.groupby("code").agg(
            pnl=("pnl", "sum"),
            trades=("pnl", "count"),
            win_rate=("pnl", lambda s: (s > 0).mean() * 100),
        )
        spath = p / f"{prefix}_by_symbol.csv"
        by_sym.to_csv(spath, encoding="utf-8-sig")
        paths["by_symbol"] = str(spath)

        if tickers_sectors:
            tc["sector"] = tc["code"].map(lambda c: tickers_sectors.get(c, "Unknown"))
            by_sec = tc.groupby("sector").agg(
                pnl=("pnl", "sum"),
                trades=("pnl", "count"),
                win_rate=("pnl", lambda s: (s > 0).mean() * 100),
            )
            secpath = p / f"{prefix}_by_sector.csv"
            by_sec.to_csv(secpath, encoding="utf-8-sig")
            paths["by_sector"] = str(secpath)

        tpath = p / f"{prefix}_trades.csv"
        tdf.to_csv(tpath, index=False, encoding="utf-8-sig")
        paths["trades"] = str(tpath)

    mf = pd.DataFrame([metrics])
    mpath = p / f"{prefix}_metrics.csv"
    mf.to_csv(mpath, index=False, encoding="utf-8-sig")
    paths["metrics"] = str(mpath)

    return paths


def write_comparison_report(
    before: Dict,
    after: Dict,
    path: str,
    label_before: str = "before",
    label_after: str = "after",
) -> None:
    lines = [
        "# 改善前後 比較レポート",
        "",
        "| 指標 | " + label_before + " | " + label_after + " |",
        "|------|------------|-----------|",
    ]
    keys = [
        "trade_count",
        "win_rate_pct",
        "avg_win_pct",
        "avg_loss_pct",
        "risk_reward",
        "profit_factor",
        "max_drawdown_pct",
        "annual_return_pct",
        "avg_holding_days",
        "max_consecutive_losses",
        "avg_assumed_slippage_pct",
    ]
    names = {
        "trade_count": "総トレード数（部分決済含む）",
        "win_rate_pct": "勝率%",
        "avg_win_pct": "平均利益率%",
        "avg_loss_pct": "平均損失率%",
        "risk_reward": "リスクリワード（金額）",
        "profit_factor": "PF",
        "max_drawdown_pct": "最大DD%",
        "annual_return_pct": "年率リターン%",
        "avg_holding_days": "平均保有日数",
        "max_consecutive_losses": "最大連敗数",
        "avg_assumed_slippage_pct": "平均スリッページ（仮定%）",
    }
    for k in keys:
        b = before.get(k, "")
        a = after.get(k, "")
        if isinstance(b, float):
            b = round(b, 4)
        if isinstance(a, float):
            a = round(a, 4)
        lines.append(f"| {names.get(k, k)} | {b} | {a} |")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    print("バックテストエンジン: 波乗り × cleartrade")
    print("ローカル検証: python -m trade_rules.run_cleartrade_yfinance --tickers 7203.T")
