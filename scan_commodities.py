"""
商品先物 ゴールデンクロス スキャナー
金・銀・原油・天然ガス・農産物などの先物 MA5/MA10 を計算し
results/commodities.json に出力する
"""
import yfinance as yf
import json
import datetime
import time
import os

# =============================================
# 商品先物銘柄リスト
# =============================================
TICKERS = [
    # 貴金属
    ("GC=F",  "金（ゴールド）"),
    ("SI=F",  "銀（シルバー）"),
    ("HG=F",  "銅"),
    ("PL=F",  "プラチナ"),
    ("PA=F",  "パラジウム"),
    # エネルギー
    ("CL=F",  "WTI原油"),
    ("BZ=F",  "ブレント原油"),
    ("NG=F",  "天然ガス"),
    ("RB=F",  "ガソリン"),
    ("HO=F",  "暖房油"),
    # 農産物
    ("ZC=F",  "トウモロコシ"),
    ("ZW=F",  "小麦"),
    ("ZS=F",  "大豆"),
    ("ZL=F",  "大豆油"),
    ("ZM=F",  "大豆ミール"),
    ("KC=F",  "コーヒー"),
    ("CT=F",  "綿花"),
    ("SB=F",  "砂糖"),
    ("CC=F",  "カカオ"),
    ("OJ=F",  "オレンジジュース"),
    # 畜産
    ("LE=F",  "生牛"),
    ("HE=F",  "豚"),
]

def calc_ma(prices, n):
    if len(prices) < n:
        return None
    return sum(prices[-n:]) / n

def analyze(prices, volumes=None):
    """MA5/MA10 の GC・予見スコアを計算"""
    if not prices or len(prices) < 12:
        return None

    ma5_t0  = calc_ma(prices, 5)
    ma10_t0 = calc_ma(prices, 10)
    prev    = prices[:-1]
    ma5_t1  = calc_ma(prev, 5)
    ma10_t1 = calc_ma(prev, 10)
    prev2   = prices[:-2]
    ma5_t2  = calc_ma(prev2, 5)
    ma10_t2 = calc_ma(prev2, 10)

    if not all([ma5_t0, ma10_t0, ma5_t1, ma10_t1, ma5_t2, ma10_t2]):
        return None

    diff_t0 = ma5_t0 - ma10_t0
    diff_t1 = ma5_t1 - ma10_t1
    diff_t2 = ma5_t2 - ma10_t2
    diff_pct = diff_t0 / ma10_t0 * 100

    gc_today   = diff_t1 <= 0 and diff_t0 > 0
    ma5_above  = diff_t0 > 0
    conv_speed = diff_t0 - diff_t1
    conv_speed2= diff_t1 - diff_t2
    is_conv    = conv_speed < 0
    is_accel   = conv_speed < conv_speed2
    ma5_slope  = ma5_t0 - ma5_t1
    ma10_slope = ma10_t0 - ma10_t1
    ma5_rising = ma5_slope > 0
    ma5_faster = ma5_slope > ma10_slope

    est_days = None
    if is_conv and conv_speed != 0 and diff_t0 != 0:
        n = -diff_t0 / conv_speed
        if 0 < n <= 30:
            est_days = int(n) + 1

    # 出来高確認（直近20日平均の1.5倍以上）
    vol_ratio = None
    vol_confirmed = False
    if volumes and len(volumes) >= 21:
        vol_avg20 = sum(volumes[-21:-1]) / 20
        if vol_avg20 > 0:
            vol_ratio = round(volumes[-1] / vol_avg20, 2)
            vol_confirmed = vol_ratio >= 1.5

    # 予見スコア
    score = 0
    abs_pct = abs(diff_pct)
    if   abs_pct <= 0.3: score += 40
    elif abs_pct <= 0.7: score += 32
    elif abs_pct <= 1.5: score += 22
    elif abs_pct <= 3.0: score += 12
    elif abs_pct <= 5.0: score += 5
    if is_conv:       score += 15
    if is_accel:      score += 15
    if ma5_rising:    score += 15
    if ma5_faster:    score += 15
    if ma10_slope > 0: score += 10
    if vol_confirmed and not gc_today: score += 15
    if gc_today:      score = 0

    rank = "GC" if gc_today else "S" if score >= 75 else "A" if score >= 50 else "B" if score >= 30 else "C"

    return {
        "close":         round(prices[-1], 3),
        "ma5":           round(ma5_t0, 3),
        "ma10":          round(ma10_t0, 3),
        "diff_pct":      round(diff_pct, 2),
        "gc_today":      gc_today,
        "ma5_above":     ma5_above,
        "is_conv":       is_conv,
        "is_accel":      is_accel,
        "ma5_rising":    ma5_rising,
        "ma5_faster":    ma5_faster,
        "est_days":      est_days,
        "score":         score,
        "rank":          rank,
        "ma5_slope":     round(ma5_slope, 3),
        "ma10_slope":    round(ma10_slope, 3),
        "vol_ratio":     vol_ratio,
        "vol_confirmed": vol_confirmed,
    }

def fetch_closes(ticker, period, interval):
    """yfinance で終値リストを取得"""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if df.empty or len(df) < 12:
            return None
        return df["Close"].dropna().tolist()
    except Exception as e:
        print(f"  ⚠ {ticker}: {e}")
        return None

def fetch_ohlcv(ticker, period, interval):
    """終値と出来高を1回のAPIコールで取得"""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if df.empty or len(df) < 12:
            return None, None
        closes = df["Close"].dropna().tolist()
        volumes = df["Volume"].tolist()
        return closes, volumes
    except Exception as e:
        print(f"  ⚠ {ticker}: {e}")
        return None, None

def check_market_regime(index_code="DJP"):
    """商品市場全体のトレンドを確認（Bloomberg商品指数ETF MA20 vs MA50）"""
    try:
        df = yf.Ticker(index_code).history(period="6mo", interval="1d")
        if df.empty or len(df) < 50:
            return {"bullish": True, "detail": "データ不足"}
        closes = df["Close"].dropna().tolist()
        ma20 = sum(closes[-20:]) / 20
        ma50 = sum(closes[-50:]) / 50
        bullish = ma20 > ma50
        return {
            "bullish": bullish,
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "index": index_code,
            "detail": "上昇トレンド" if bullish else "⚠ 下降トレンド",
        }
    except Exception as e:
        print(f"  商品市場トレンド取得失敗: {e}")
        return {"bullish": True, "detail": "取得失敗"}

def scan_all(timeframe, weekly_lookup=None, market_regime=None):
    """全商品をスキャンして結果リストを返す"""
    cfg = {
        "1d":  {"period": "3mo",  "interval": "1d"},
        "1wk": {"period": "2y",   "interval": "1wk"},
        "1mo": {"period": "5y",   "interval": "1mo"},
    }[timeframe]

    results = []
    total = len(TICKERS)
    for i, (code, name) in enumerate(TICKERS):
        print(f"  [{i+1:2}/{total}] {code} {name}", end=" ")

        if timeframe == "1d":
            closes, volumes = fetch_ohlcv(code, cfg["period"], cfg["interval"])
        else:
            closes = fetch_closes(code, cfg["period"], cfg["interval"])
            volumes = None

        if closes is None:
            print("SKIP")
            time.sleep(0.5)
            continue

        sig = analyze(closes, volumes)
        if sig:
            # 週足整合フィルター
            weekly_aligned = weekly_lookup.get(code, False) if weekly_lookup else None
            if weekly_aligned and not sig["gc_today"]:
                sig["score"] += 15
                sig["rank"] = (
                    "S" if sig["score"] >= 75 else
                    "A" if sig["score"] >= 50 else
                    "B" if sig["score"] >= 30 else "C"
                )
            sig["weekly_aligned"] = weekly_aligned

            # 相場全体フィルター
            market_caution = False
            if (market_regime and not market_regime.get("bullish", True)
                    and not sig["gc_today"]):
                sig["score"] = max(0, sig["score"] - 20)
                sig["rank"] = (
                    "S" if sig["score"] >= 75 else
                    "A" if sig["score"] >= 50 else
                    "B" if sig["score"] >= 30 else "C"
                )
                market_caution = True
            sig["market_caution"] = market_caution

            results.append({"code": code, "name": name, **sig})
            flags = ("W✓" if weekly_aligned else "") + (" V✓" if sig.get("vol_confirmed") else "") + (" ⚠市場" if market_caution else "")
            print(f"rank={sig['rank']} gc={sig['gc_today']} score={sig['score']}{flags}")
        else:
            print("no data")
        time.sleep(0.5)

    return results

def main():
    os.makedirs("results", exist_ok=True)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    now_str = now.strftime("%Y-%m-%d %H:%M JST")

    output = {
        "generated_at": now_str,
        "market": "商品先物",
        "timeframes": {}
    }

    # 商品市場全体トレンド確認（Bloomberg商品指数ETF）
    print(f"\n{'='*50}")
    print(f"商品市場トレンド確認中...")
    print(f"{'='*50}")
    regime = check_market_regime("DJP")
    print(f"  商品指数(DJP): MA20={regime['ma20']} / MA50={regime['ma50']} → {regime['detail']}")
    output["market_regime"] = regime

    # 週足スキャン（日足フィルターに使用）
    print(f"\n{'='*50}")
    print(f"商品先物 週足スキャン開始 ({now_str})")
    print(f"{'='*50}")
    wk_results = scan_all("1wk")
    weekly_lookup = {r["code"]: r.get("ma5_above", False) for r in wk_results}
    output["timeframes"]["1wk"] = wk_results

    for tf in ["1d", "1mo"]:
        print(f"\n{'='*50}")
        print(f"商品先物 スキャン開始: {tf} ({now_str})")
        print(f"{'='*50}")
        results = scan_all(
            tf,
            weekly_lookup=weekly_lookup if tf == "1d" else None,
            market_regime=regime if tf == "1d" else None,
        )
        output["timeframes"][tf] = results

        gc     = [r for r in results if r["gc_today"]]
        rank_s = [r for r in results if r["rank"] == "S"]
        wa     = [r for r in results if r.get("weekly_aligned")]
        vol    = [r for r in results if r.get("vol_confirmed")]
        print(f"\n  GC本日: {len(gc)}件  Sランク: {len(rank_s)}件  週足整合: {len(wa)}件  出来高急増: {len(vol)}件  合計: {len(results)}件")

    with open("results/commodities.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ results/commodities.json 保存完了")

if __name__ == "__main__":
    main()
