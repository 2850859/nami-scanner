"""
GCトラッカー: ゴールデンクロス発生銘柄の追跡・勝率集計

- GC本日の銘柄を data/gc_tracker.csv に記録
- 5日後・10日後・20日後の株価を自動更新
- 勝率統計を data/gc_stats.json に出力（メール送信で使用）

営業日の近似（週5日 ≒ 暦7日）:
  5営業日  ≒  8暦日
  10営業日 ≒ 15暦日
  20営業日 ≒ 29暦日
"""
import os
import json
import csv
import datetime
import yfinance as yf

TRACKER_PATH = "data/gc_tracker.csv"
STATS_PATH   = "data/gc_stats.json"

FIELDNAMES = [
    "gc_date", "market", "code", "name", "gc_price",
    "d5_price", "d5_pct",
    "d10_price", "d10_pct",
    "d20_price", "d20_pct",
]

# N営業日後の判定に使う最小暦日数
ELAPSED_THRESHOLDS = {
    "d5":  (8,  "d5_price",  "d5_pct",  5),
    "d10": (15, "d10_price", "d10_pct", 10),
    "d20": (29, "d20_price", "d20_pct", 20),
}


# ──────────────────────────────────────────
def load_tracker() -> list[dict]:
    if not os.path.exists(TRACKER_PATH):
        return []
    with open(TRACKER_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_tracker(rows: list[dict]):
    os.makedirs(os.path.dirname(TRACKER_PATH), exist_ok=True)
    with open(TRACKER_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def get_current_price(code: str) -> float | None:
    try:
        df = yf.Ticker(code).history(period="3d", interval="1d")
        if not df.empty:
            return round(float(df["Close"].iloc[-1]), 2)
    except Exception as e:
        print(f"    価格取得失敗 {code}: {e}")
    return None


# ──────────────────────────────────────────
def add_new_gcs(rows: list[dict], today_str: str):
    """今日のスキャン結果からGC銘柄を追加"""
    existing = {(r["gc_date"], r["code"]) for r in rows}

    for market, path in [("JPX400", "results/jpx400.json"), ("SP500", "results/sp500.json")]:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for r in data.get("timeframes", {}).get("1d", []):
            if not r.get("gc_today"):
                continue
            key = (today_str, r["code"])
            if key in existing:
                continue
            rows.append({
                "gc_date":  today_str,
                "market":   market,
                "code":     r["code"],
                "name":     r["name"],
                "gc_price": r["close"],
                "d5_price": "", "d5_pct":  "",
                "d10_price":"", "d10_pct": "",
                "d20_price":"", "d20_pct": "",
            })
            existing.add(key)
            print(f"  + 追加: [{market}] {r['code']} {r['name']}  close={r['close']}")


def update_prices(rows: list[dict], today: datetime.date):
    """既存エントリの追跡価格を更新（未記入のもの）"""
    for row in rows:
        gc_date = datetime.date.fromisoformat(row["gc_date"])
        elapsed = (today - gc_date).days

        for key, (min_days, col_p, col_pct, label) in ELAPSED_THRESHOLDS.items():
            if elapsed < min_days:
                continue
            if row.get(col_p):
                continue  # 既に記録済み

            price = get_current_price(row["code"])
            if price is None:
                continue
            gc_price = float(row["gc_price"])
            pct = round((price - gc_price) / gc_price * 100, 2)
            row[col_p]   = price
            row[col_pct] = pct
            sign = "+" if pct >= 0 else ""
            print(f"  更新: {row['code']} {label}日後 → {price}  ({sign}{pct}%)")


# ──────────────────────────────────────────
def calc_stats(rows: list[dict]) -> dict:
    """期間ごとの勝率・平均騰落率を集計"""
    stats = {}
    for key, (_, _, col_pct, label) in ELAPSED_THRESHOLDS.items():
        completed = [r for r in rows if r.get(col_pct) != ""]
        if not completed:
            continue
        pcts  = [float(r[col_pct]) for r in completed]
        wins  = [p for p in pcts if p > 0]
        stats[str(label)] = {
            "total":    len(completed),
            "wins":     len(wins),
            "win_rate": round(len(wins) / len(completed) * 100, 1),
            "avg_pct":  round(sum(pcts) / len(pcts), 2),
        }
    return stats


# ──────────────────────────────────────────
def main():
    today     = datetime.date.today()
    today_str = today.isoformat()

    print(f"\n{'='*50}")
    print(f"GCトラッカー更新: {today_str}")
    print(f"{'='*50}")

    rows = load_tracker()
    add_new_gcs(rows, today_str)
    update_prices(rows, today)
    save_tracker(rows)

    stats = calc_stats(rows)

    # 統計をJSONで保存（send_mail.pyで参照）
    os.makedirs("data", exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"updated_at": today_str, "total": len(rows), "stats": stats},
            f, ensure_ascii=False, indent=2
        )

    print(f"\n  累計追跡: {len(rows)} 件")
    for label, s in stats.items():
        sign = "+" if s["avg_pct"] >= 0 else ""
        print(f"  {label}日後  勝率 {s['win_rate']}%  ({s['wins']}/{s['total']}件)  平均 {sign}{s['avg_pct']}%")
    print(f"\n  保存完了: {TRACKER_PATH} / {STATS_PATH}")


if __name__ == "__main__":
    main()
