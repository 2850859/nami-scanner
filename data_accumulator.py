"""
データ蓄積モジュール
- 時系列データ（Parquet）に追記
- シグナルイベント（JSONL）に追記
"""
import os
import json
import datetime
import pandas as pd
from pathlib import Path


def append_history(market: str, timeframe: str, results: list, scan_date: str):
    """
    時系列ヒストリーに当日のデータを追記する
    
    Parameters
    ----------
    market : str       'jpx400' or 'sp500'
    timeframe : str    '1d' / '1wk' / '1mo'
    results : list     analyze() の結果リスト
    scan_date : str    'YYYY-MM-DD'
    """
    if not results:
        return

    os.makedirs("data", exist_ok=True)
    path = Path(f"data/{market}_history_{timeframe}.parquet")

    def _to_bool(v, default=False):
        if v is None:
            return default
        return bool(v)

    # 当日分のDataFrameを作成
    rows = []
    for r in results:
        # スキーマ差分に強くする（scan_* 側の項目追加/削除で落ちない）
        rows.append({
            "date":        scan_date,
            "market":      market,
            "timeframe":   timeframe,
            "code":        r["code"],
            "name":        r["name"],
            "close":       float(r.get("close", 0)),
            "ma5":         float(r.get("ma5", 0)),
            "ma10":        float(r.get("ma10", 0)),
            "diff_pct":    float(r.get("diff_pct", 0)),
            "gc_today":    _to_bool(r.get("gc_today"), False),
            "ma5_above":   _to_bool(r.get("ma5_above"), False),
            "is_conv":     _to_bool(r.get("is_conv"), False),
            "is_accel":    _to_bool(r.get("is_accel"), False),
            "ma5_rising":  _to_bool(r.get("ma5_rising"), False),
            "ma5_faster":  _to_bool(r.get("ma5_faster"), False),
            "est_days":    int(r["est_days"]) if r.get("est_days") not in (None, "") else None,
            "score":       int(r.get("score", 0)),
            "rank":        r.get("rank", "C"),
            "ma5_slope":   float(r.get("ma5_slope", 0)),
            "ma10_slope":  float(r.get("ma10_slope", 0)),
        })
    df_new = pd.DataFrame(rows)

    # 既存のParquetがあれば読み込んで追記
    if path.exists():
        try:
            df_old = pd.read_parquet(path)
            # 同じ日付・銘柄の重複を排除（最新で上書き）
            df_old = df_old[~(
                (df_old["date"] == scan_date) &
                (df_old["timeframe"] == timeframe)
            )]
            df = pd.concat([df_old, df_new], ignore_index=True)
        except Exception as e:
            print(f"  ⚠ 既存Parquet読み込み失敗（新規作成します）: {e}")
            df = df_new
    else:
        df = df_new

    # 保存
    df.to_parquet(path, compression="snappy", index=False)
    print(f"  💾 {path}: 累計 {len(df):,} 行")


def append_signals(market: str, results: list, scan_date: str):
    """
    シグナル発生イベントを JSONL に追記する
    （GC本日 または Sランク のみ記録）
    """
    if not results:
        return

    os.makedirs("data", exist_ok=True)
    path = Path(f"data/{market}_signals.jsonl")

    new_count = 0
    with open(path, "a", encoding="utf-8") as f:
        for r in results:
            # シグナル候補のみ記録
            if not (bool(r.get("gc_today")) or r.get("rank") in ("S", "A")):
                continue

            event = {
                "date":      scan_date,
                "market":    market,
                "code":      r["code"],
                "name":      r["name"],
                "event":     "GC" if bool(r.get("gc_today")) else f"PRE_{r.get('rank', 'C')}",
                "close":     float(r.get("close", 0)),
                "ma5":       float(r.get("ma5", 0)),
                "ma10":      float(r.get("ma10", 0)),
                "diff_pct":  float(r.get("diff_pct", 0)),
                "score":     int(r.get("score", 0)),
                "rank":      r.get("rank", "C"),
                "est_days":  int(r["est_days"]) if r.get("est_days") not in (None, "") else None,
            }
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            new_count += 1

    print(f"  📝 {path}: 今日のシグナル {new_count} 件を追記")


def append_all(market: str, output: dict):
    """
    main() の最後で呼び出すラッパー
    output = {"generated_at": "...", "market": "...", "timeframes": {"1d": [...], ...}}
    """
    # スキャン日（取引日ベース）
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    scan_date = now.strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"  📊 データ蓄積開始")
    print(f"{'='*50}")

    market_lower = market.lower().replace("&", "").replace(" ", "")

    # 全タイムフレームの履歴を追記
    for tf, results in output.get("timeframes", {}).items():
        append_history(market_lower, tf, results, scan_date)

    # シグナルイベント（日足のみ記録）
    daily = output.get("timeframes", {}).get("1d", [])
    append_signals(market_lower, daily, scan_date)

    print(f"  ✅ データ蓄積完了\n")
