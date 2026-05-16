"""
波乗り×cleartrade バックテストを yfinance で実行（TOPIX 近似）。

例:
  python -m trade_rules.run_cleartrade_yfinance --tickers 7203.T 6758.T 9984.T
  python -m trade_rules.run_cleartrade_yfinance --tickers AAPL MSFT --entry-mode compare --out-dir results
  python -m trade_rules.run_cleartrade_yfinance --tickers 7203.T --period 3y --notify
    （完了時に Resend でメール。要 RESEND_API_KEY / NOTIFY_EMAIL）
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import yfinance as yf

from trade_rules.backtest_engine import (
    Backtester,
    EntryMode,
    SignalDetector,
    StrategyConfig,
    calculate_metrics,
    export_backtest_reports,
    trades_to_dataframe,
    write_comparison_report,
)


US_SECTOR_ETF = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


def _download_ohlcv(ticker: str, period: str) -> pd.DataFrame | None:
    try:
        raw = yf.download(
            ticker, period=period, interval="1d", progress=False, auto_adjust=True
        )
    except Exception as e:
        print(f"  SKIP {ticker}: {e}")
        return None
    if raw.empty or len(raw) < 60:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    raw = raw.rename(columns=str.lower)
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    return raw[["open", "high", "low", "close", "volume"]].copy()


def _download_topix(period: str) -> pd.DataFrame:
    for sym in ("^TOPX", "1306.T", "TOPIX.T"):
        df = _download_ohlcv(sym, period)
        if df is not None and len(df) > 60:
            print(f"  TOPIX proxy: {sym}")
            return df[["close"]]
    raise SystemExit("TOPIX series download failed.")


def fetch_sector_map(tickers: list[str], pause: float = 0.08) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            out[t] = info.get("sector") or info.get("category") or "Unknown"
        except Exception:
            out[t] = "Unknown"
        time.sleep(pause)
    return out


def build_sector_gates(
    panel: Dict[str, pd.DataFrame],
    sector_by_ticker: Dict[str, str],
    topix_close: pd.Series,
    period: str,
) -> Dict[str, pd.Series]:
    common: pd.Index | None = None
    for d in panel.values():
        common = d.index if common is None else common.intersection(d.index)
    common = common.sort_values()
    tc = topix_close.reindex(common).ffill()

    sec_tickers: Dict[str, list] = defaultdict(list)
    for t in panel:
        sec_tickers[sector_by_ticker.get(t, "Unknown")].append(t)

    gates: Dict[str, pd.Series] = {}

    for sec, tickers in sec_tickers.items():
        t0 = tickers[0]
        bench_sym = None
        if not str(t0).endswith(".T"):
            bench_sym = US_SECTOR_ETF.get(sec)

        bench_close = None
        if bench_sym:
            bdf = _download_ohlcv(bench_sym, period)
            if bdf is not None:
                bench_close = bdf["close"].reindex(common).ffill()
        if bench_close is None or bench_close.isna().all():
            bench_close = tc

        sma20 = bench_close.rolling(20, min_periods=1).mean()
        bench_ok = bench_close > sma20

        dates = list(common)
        breadth_vals = []
        for i, dt in enumerate(dates):
            if i == 0:
                breadth_vals.append(1.0)
                continue
            prev = dates[i - 1]
            adv = 0
            n = 0
            for tk in tickers:
                if tk not in panel:
                    continue
                dft = panel[tk]
                if dt not in dft.index or prev not in dft.index:
                    continue
                n += 1
                if float(dft.loc[dt, "close"]) > float(dft.loc[prev, "close"]):
                    adv += 1
            breadth_vals.append((adv / n) if n > 1 else 1.0)

        breadth = pd.Series(breadth_vals, index=common)
        gate = (breadth >= 0.5) | bench_ok.fillna(False)
        gate = gate.fillna(False)
        for tk in tickers:
            if tk in panel:
                gates[tk] = gate

    return gates


def tag_market_regime(topix_close: pd.Series) -> pd.Series:
    c = topix_close
    ma50 = c.rolling(50, min_periods=1).mean()
    ma200 = c.rolling(200, min_periods=1).mean()

    def _tag(row):
        ci, m50, m200 = row["c"], row["m50"], row["m200"]
        if pd.isna(m50) or pd.isna(m200):
            return "unknown"
        if ci > m50 > m200:
            return "bull"
        if ci < m50 < m200:
            return "bear"
        return "sideways"

    z = pd.DataFrame({"c": c, "m50": ma50, "m200": ma200})
    return z.apply(_tag, axis=1)


def export_regime_trade_stats(
    trades_df: pd.DataFrame,
    regime_series: pd.Series,
    path: str,
) -> None:
    if trades_df.empty:
        return
    tdf = trades_df.copy()
    tdf["entry_date"] = pd.to_datetime(tdf["entry_date"])
    reg = regime_series.reindex(pd.to_datetime(tdf["entry_date"])).ffill()
    tdf["regime"] = reg.values
    g = tdf.groupby("regime", dropna=False).agg(
        pnl=("pnl", "sum"), n=("pnl", "count"), win=("pnl", lambda s: (s > 0).mean())
    )
    g.to_csv(path, encoding="utf-8-sig")


def run_single(
    panel: Dict[str, pd.DataFrame],
    topix: pd.DataFrame,
    cfg: StrategyConfig,
    capital: float,
    sector_map: Dict[str, str] | None,
    period: str,
) -> tuple:
    sector_gates = None
    if cfg.sector_filter_enabled and sector_map:
        tc = topix["close"]
        sector_gates = build_sector_gates(panel, sector_map, tc, period)
        print(f"  sector gates built for {len(sector_gates)} tickers")

    bt = Backtester(cfg, initial_capital=capital)
    result = bt.run(panel, topix, sector_gates=sector_gates)
    metrics = calculate_metrics(result, capital)
    return result, metrics


def _load_universe(name: str) -> list[str]:
    """jpx400 / sp500 / all の全ティッカーリストを返す。"""
    tickers: list[str] = []
    if name in ("jpx400", "all"):
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from scan_jpx400 import TICKERS as JPX_TICKERS
            tickers += [t for t, _ in JPX_TICKERS]
        except Exception as e:
            print(f"  [WARN] JPX400リスト読込失敗: {e}")
    if name in ("sp500", "all"):
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from scan_sp500 import SP500_TICKERS
            tickers += [t for t, _ in SP500_TICKERS]
        except Exception as e:
            print(f"  [WARN] SP500リスト読込失敗: {e}")
    return tickers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="個別ティッカー指定（--universe と併用可・上書き）")
    ap.add_argument("--universe", choices=["jpx400", "sp500", "all"], default=None,
                    help="全銘柄ユニバース: jpx400 / sp500 / all")
    ap.add_argument("--period", default="3y")
    ap.add_argument("--capital", type=float, default=100_000_000.0)
    ap.add_argument("--out", default="results/cleartrade_backtest.json")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--prefix", default="cleartrade")
    ap.add_argument(
        "--entry-mode",
        choices=["next_open", "close", "next_vwap", "compare"],
        default="next_open",
    )
    ap.add_argument("--sector-filter", action="store_true")
    ap.add_argument("--no-atr-pullback", action="store_true", help="legacy %% dip")
    ap.add_argument(
        "--no-volume-reexpand",
        action="store_true",
        help="E1/E2 without volume vs yesterday +20%% (diagnostics)",
    )
    ap.add_argument(
        "--no-perfect-order",
        action="store_true",
        help="disable SMA5 > SMA10 > SMA20 trend filter (cleartrade only)",
    )
    ap.add_argument(
        "--legacy-cleartrade",
        action="store_true",
        help="use legacy cleartrade rules instead of v2.0 screening",
    )
    ap.add_argument("--compare-baseline", type=str, default="", help="baseline JSON path")
    ap.add_argument(
        "--notify",
        action="store_true",
        help="完了時に Resend で NOTIFY_EMAIL へメール（要 RESEND_API_KEY）",
    )
    args = ap.parse_args()

    if not args.tickers and not args.universe:
        ap.error("--tickers または --universe を指定してください")

    target_tickers: list[str] = []
    if args.universe:
        target_tickers = _load_universe(args.universe)
        print(f"  Universe: {args.universe}  ({len(target_tickers)} 銘柄)")
    if args.tickers:
        target_tickers = args.tickers  # 明示指定で上書き

    topix = _download_topix(args.period)
    panel: Dict[str, pd.DataFrame] = {}
    total = len(target_tickers)
    for idx, t in enumerate(target_tickers, 1):
        print(f"  [{idx:3}/{total}] {t}", end=" ")
        d = _download_ohlcv(t, args.period)
        if d is not None:
            panel[t] = d
            print(f"rows={len(d)}")
        else:
            print("SKIP")
        if total > 10:
            time.sleep(0.15)  # レート制限対策

    if not panel:
        raise SystemExit("No valid tickers")

    # JP / US を分けて共通日を算出（混在時はそれぞれの取引日を維持）
    from trade_rules.wave_screening_v2 import infer_market
    jp_panel = {k: v for k, v in panel.items() if infer_market(k) == "JP"}
    us_panel = {k: v for k, v in panel.items() if infer_market(k) == "US"}

    def _align_panel(sub: Dict[str, pd.DataFrame], topix_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        if not sub:
            return {}
        common: pd.Index | None = None
        for d in sub.values():
            common = d.index if common is None else common.intersection(d.index)
        common = common.sort_values()
        t = topix_df.reindex(common, method="ffill").dropna()
        common = t.index
        return {k: v.loc[common] for k, v in sub.items()}

    if jp_panel and us_panel:
        # JP + US 混在: 共通日で揃える
        panel_aligned = _align_panel(panel, topix)
        topix_aligned = topix.reindex(list(panel_aligned.values())[0].index, method="ffill").dropna()
        panel = panel_aligned
        topix = topix_aligned
    elif jp_panel:
        panel = _align_panel(jp_panel, topix)
        topix = topix.reindex(list(panel.values())[0].index, method="ffill").dropna()
    else:
        panel = _align_panel(us_panel, topix)
        topix = topix.reindex(list(panel.values())[0].index, method="ffill").dropna()

    sector_map = fetch_sector_map(list(panel.keys())) if args.sector_filter else None

    if args.legacy_cleartrade:
        base_cfg = StrategyConfig(
            strategy_rules="cleartrade",
            stop_loss_pct=0.05,
            max_positions=3,
        )
    else:
        base_cfg = StrategyConfig(strategy_rules="v2")
    base_cfg.sector_filter_enabled = bool(args.sector_filter)
    if args.no_atr_pullback:
        base_cfg.use_atr_pullback = False
    if args.no_volume_reexpand:
        base_cfg.require_volume_reexpand = False
    if args.no_perfect_order:
        base_cfg.require_perfect_order = False

    det = SignalDetector(base_cfg)
    raw_signals = 0
    for _sym, _df in panel.items():
        raw_signals += len(det.detect_signals(det.calculate_indicators(_df, topix)))
    print(f"  raw_entry_signals (before portfolio, mode={args.entry_mode}): {raw_signals}")

    modes: list[EntryMode] = (
        ["next_open", "close", "next_vwap"]
        if args.entry_mode == "compare"
        else [args.entry_mode]  # type: ignore[list-item]
    )

    all_results: Dict[str, tuple] = {}
    for mode in modes:
        cfg = StrategyConfig(
            strategy_rules=base_cfg.strategy_rules,
            entry_mode=mode,
            sector_filter_enabled=base_cfg.sector_filter_enabled,
            use_atr_pullback=base_cfg.use_atr_pullback,
            require_volume_reexpand=base_cfg.require_volume_reexpand,
            require_perfect_order=base_cfg.require_perfect_order,
            stop_loss_pct=base_cfg.stop_loss_pct,
            max_positions=base_cfg.max_positions,
            position_allocation_pct=base_cfg.position_allocation_pct,
        )
        result, metrics = run_single(
            panel, topix, cfg, args.capital, sector_map, args.period
        )
        all_results[mode] = (result, metrics)
        print(f"\n=== entry_mode={mode} ===")
        print(json.dumps(metrics, ensure_ascii=False, indent=2, default=str))

    primary_mode = "next_open" if args.entry_mode == "compare" else args.entry_mode
    result, metrics = all_results[primary_mode]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out_payload = {
        "metrics": metrics,
        "n_trades_detail": len(result["trades"]),
        "tickers": list(panel.keys()),
        "period": args.period,
        "entry_mode": primary_mode,
        "compare": {
            k: v[1] for k, v in all_results.items()
        }
        if len(all_results) > 1
        else None,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_payload, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")
    print(f"\nSaved summary JSON: {args.out}")

    paths = export_backtest_reports(
        result,
        metrics,
        sector_map,
        args.out_dir,
        prefix=args.prefix,
    )
    for k, v in paths.items():
        print(f"  CSV [{k}]: {v}")

    tdf = trades_to_dataframe(result["trades"])
    regime_s = tag_market_regime(topix["close"])
    rpath = str(Path(args.out_dir) / f"{args.prefix}_by_regime.csv")
    export_regime_trade_stats(tdf, regime_s, rpath)
    print(f"  CSV [regime]: {rpath}")

    if args.compare_baseline:
        try:
            with open(args.compare_baseline, encoding="utf-8") as f:
                base_js = json.load(f)
            bm = base_js.get("metrics", base_js)
            cmp_path = str(Path(args.out_dir) / f"{args.prefix}_comparison_vs_baseline.md")
            write_comparison_report(bm, metrics, cmp_path, "baseline", "current")
            print(f"  Report: {cmp_path}")
        except Exception as e:
            print(f"  [WARN] comparison report skipped: {e}")

    if metrics.get("error"):
        print()
        print("[HINT] No trades = filters strict or short period.")
        print("  Try: --period 5y  --tickers (more)  or  --no-atr-pullback")

    if args.notify:
        try:
            import send_mail

            send_mail.notify_backtest_email(
                summary_json_path=args.out,
                out_dir=args.out_dir,
                prefix=args.prefix,
                metrics=metrics,
                tickers=list(panel.keys()),
                period=args.period,
                entry_mode=primary_mode,
            )
        except Exception as e:
            print(f"  [WARN] メール通知に失敗: {e}")


if __name__ == "__main__":
    main()
