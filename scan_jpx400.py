"""
JPX400 ゴールデンクロス スキャナー
日足・週足・月足の MA5/MA10 を計算し results/jpx400.json に出力
"""
import yfinance as yf
import pandas as pd
import json
import datetime
import time
import os

# =============================================
# JPX400 全401銘柄
# =============================================
TICKERS = [
    ("1332.T","ニッスイ"),("1414.T","ショーボンドHD"),("1419.T","タマホーム"),
    ("1518.T","三井松島HD"),("1605.T","INPEX"),("1662.T","石油資源開発"),
    ("1719.T","安藤・間"),("1721.T","コムシスHD"),("1801.T","大成建設"),
    ("1802.T","大林組"),("1808.T","長谷工コーポレーション"),("1812.T","鹿島建設"),
    ("1878.T","大東建託"),("1911.T","住友林業"),("1925.T","大和ハウス工業"),
    ("1928.T","積水ハウス"),("1942.T","関電工"),("1951.T","エクシオグループ"),
    ("1959.T","九電工"),("1969.T","高砂熱学工業"),("1973.T","NECネッツエスアイ"),
    ("2124.T","JAC Recruitment"),("2127.T","日本M&AセンターHD"),("2146.T","UTグループ"),
    ("2168.T","パソナグループ"),("2175.T","エス・エム・エス"),("2181.T","パーソルHD"),
    ("2201.T","森永製菓"),("2222.T","寿スピリッツ"),("2229.T","カルビー"),
    ("2264.T","森永乳業"),("2267.T","ヤクルト本社"),("2269.T","明治HD"),
    ("2282.T","日本ハム"),("2317.T","システナ"),("2327.T","日鉄ソリューションズ"),
    ("2331.T","綜合警備保障"),("2371.T","カカクコム"),("2379.T","ディップ"),
    ("2384.T","SBSホールディングス"),("2413.T","エムスリー"),("2433.T","博報堂DYホールディングス"),
    ("2502.T","アサヒグループHD"),("2503.T","キリンHD"),("2531.T","宝ホールディングス"),
    ("2587.T","サントリー食品インターナショナル"),("2670.T","エービーシー・マート"),
    ("2678.T","アスクル"),("2685.T","アダストリア"),("2702.T","日本マクドナルドHD"),
    ("2726.T","パルグループHD"),("2760.T","東京エレクトロン デバイス"),("2768.T","双日"),
    ("2782.T","セリア"),("2801.T","キッコーマン"),("2802.T","味の素"),
    ("2871.T","ニチレイ"),("2875.T","東洋水産"),("2897.T","日清食品HD"),
    ("2914.T","日本たばこ産業"),("3003.T","ヒューリック"),("3038.T","神戸物産"),
    ("3064.T","MonotaRO"),("3088.T","マツキヨCoC"),("3092.T","ZOZO"),
    ("3107.T","ダイワボウHD"),("3116.T","トヨタ紡織"),("3132.T","マクニカHD"),
    ("3141.T","ウエルシアHD"),("3148.T","クリエイトSDHD"),("3186.T","ネクステージ"),
    ("3231.T","野村不動産HD"),("3288.T","オープンハウスグループ"),("3289.T","東急不動産HD"),
    ("3291.T","飯田グループHD"),("3349.T","コスモス薬品"),("3360.T","シップヘルスケアHD"),
    ("3382.T","セブン&アイHD"),("3391.T","ツルハHD"),("3402.T","東レ"),
    ("3405.T","クラレ"),("3436.T","SUMCO"),("3465.T","ケイアイスター不動産"),
    ("3549.T","クスリのアオキHD"),("3563.T","FOOD & LIFE"),("3626.T","TIS"),
    ("3635.T","コーエーテクモHD"),("3659.T","ネクソン"),("3697.T","SHIFT"),
    ("3765.T","ガンホー"),("3769.T","GMOペイメントゲートウェイ"),("3774.T","インターネットイニシアティブ"),
    ("3861.T","王子HD"),("3923.T","ラクス"),("4021.T","日産化学"),
    ("4042.T","東ソー"),("4062.T","イビデン"),("4063.T","信越化学工業"),
    ("4088.T","エア・ウォーター"),("4091.T","日本酸素HD"),("4151.T","協和キリン"),
    ("4182.T","三菱瓦斯化学"),("4183.T","三井化学"),("4186.T","東京応化工業"),
    ("4188.T","三菱ケミカルグループ"),("4189.T","KHネオケム"),("4194.T","ビジョナル"),
    ("4202.T","ダイセル"),("4203.T","住友ベークライト"),("4204.T","積水化学工業"),
    ("4307.T","野村総合研究所"),("4368.T","扶桑化学工業"),("4401.T","ADEKA"),
    ("4403.T","日油"),("4452.T","花王"),("4502.T","武田薬品工業"),
    ("4503.T","アステラス製薬"),("4507.T","塩野義製薬"),("4516.T","日本新薬"),
    ("4519.T","中外製薬"),("4523.T","エーザイ"),("4527.T","ロート製薬"),
    ("4528.T","小野薬品工業"),("4543.T","テルモ"),("4568.T","第一三共"),
    ("4578.T","大塚HD"),("4587.T","ペプチドリーム"),("4612.T","日本ペイントHD"),
    ("4613.T","関西ペイント"),("4626.T","太陽HD"),("4661.T","オリエンタルランド"),
    ("4680.T","ラウンドワン"),("4684.T","オービック"),("4686.T","ジャストシステム"),
    ("4689.T","LINEヤフー"),("4694.T","ビー・エム・エル"),("4704.T","トレンドマイクロ"),
    ("4716.T","日本オラクル"),("4722.T","フューチャー"),("4732.T","ユー・エス・エス"),
    ("4751.T","サイバーエージェント"),("4768.T","大塚商会"),("4812.T","電通総研"),
    ("4816.T","東映アニメーション"),("4901.T","富士フイルムHD"),("4911.T","資生堂"),
    ("4912.T","ライオン"),("4967.T","小林製薬"),("4974.T","タカラバイオ"),
    ("4980.T","デクセリアルズ"),("5019.T","出光興産"),("5020.T","ENEOSホールディングス"),
    ("5021.T","コスモエネルギーHD"),("5076.T","インフロニア・HD"),("5101.T","横浜ゴム"),
    ("5105.T","TOYO TIRE"),("5108.T","ブリヂストン"),("5110.T","住友ゴム工業"),
    ("5201.T","AGC"),("5301.T","東海カーボン"),("5332.T","TOTO"),
    ("5333.T","日本碍子"),("5334.T","日本特殊陶業"),("5344.T","MARUWA"),
    ("5384.T","フジミインコーポレーテッド"),("5393.T","ニチアス"),("5401.T","日本製鉄"),
    ("5406.T","神戸製鋼所"),("5411.T","JFEホールディングス"),("5423.T","東京製鐵"),
    ("5444.T","大和工業"),("5463.T","丸一鋼管"),("5471.T","大同特殊鋼"),
    ("5480.T","日本冶金工業"),("5706.T","三井金属鉱業"),("5713.T","住友金属鉱山"),
    ("5714.T","DOWAホールディングス"),("5802.T","住友電気工業"),("5803.T","フジクラ"),
    ("5857.T","AREホールディングス"),("5929.T","三和ホールディングス"),("5947.T","リンナイ"),
    ("5991.T","日本発條"),("6005.T","三浦工業"),("6028.T","テクノプロHD"),
    ("6055.T","ジャパンマテリアル"),("6098.T","リクルートHD"),("6101.T","ツガミ"),
    ("6113.T","アマダ"),("6141.T","DMG森精機"),("6146.T","ディスコ"),
    ("6183.T","ベルシステム24 HD"),("6201.T","豊田自動織機"),("6254.T","野村マイクロ・サイエンス"),
    ("6268.T","ナブテスコ"),("6273.T","SMC"),("6301.T","小松製作所"),
    ("6302.T","住友重機械工業"),("6305.T","日立建機"),("6315.T","TOWA"),
    ("6323.T","ローツェ"),("6326.T","クボタ"),("6361.T","荏原製作所"),
    ("6367.T","ダイキン工業"),("6368.T","オルガノ"),("6383.T","ダイフク"),
    ("6417.T","SANKYO"),("6432.T","竹内製作所"),("6448.T","ブラザー工業"),
    ("6460.T","セガサミーHD"),("6465.T","ホシザキ"),("6479.T","ミネベアミツミ"),
    ("6501.T","日立製作所"),("6503.T","三菱電機"),("6504.T","富士電機"),
    ("6506.T","安川電機"),("6532.T","ベイカレント・コンサルティング"),("6544.T","ジャパンエレベーターSHD"),
    ("6586.T","マキタ"),("6632.T","JVCケンウッド"),("6645.T","オムロン"),
    ("6670.T","MCJ"),("6701.T","日本電気（NEC）"),("6702.T","富士通"),
    ("6723.T","ルネサスエレクトロニクス"),("6724.T","セイコーエプソン"),("6728.T","アルバック"),
    ("6752.T","パナソニック HD"),("6758.T","ソニーグループ"),("6762.T","TDK"),
    ("6787.T","メイコー"),("6806.T","ヒロセ電機"),("6841.T","横河電機"),
    ("6845.T","アズビル"),("6849.T","日本光電工業"),("6856.T","堀場製作所"),
    ("6857.T","アドバンテスト"),("6861.T","キーエンス"),("6869.T","シスメックス"),
    ("6890.T","フェローテックHD"),("6902.T","デンソー"),("6920.T","レーザーテック"),
    ("6951.T","日本電子"),("6954.T","ファナック"),("6963.T","ローム"),
    ("6965.T","浜松ホトニクス"),("6966.T","三井ハイテック"),("6967.T","新光電気工業"),
    ("6971.T","京セラ"),("6976.T","太陽誘電"),("6981.T","村田製作所"),
    ("6988.T","日東電工"),("7011.T","三菱重工業"),("7071.T","アンビスHD"),
    ("7105.T","三菱ロジスネクスト"),("7148.T","FPG"),("7164.T","全国保証"),
    ("7167.T","めぶきフィナンシャルG"),("7186.T","コンコルディアFG"),("7202.T","いすゞ自動車"),
    ("7203.T","トヨタ自動車"),("7211.T","三菱自動車工業"),("7242.T","カヤバ"),
    ("7259.T","アイシン"),("7261.T","マツダ"),("7267.T","本田技研工業"),
    ("7269.T","スズキ"),("7270.T","SUBARU"),("7272.T","ヤマハ発動機"),
    ("7276.T","小糸製作所"),("7282.T","豊田合成"),("7309.T","シマノ"),
    ("7419.T","ノジマ"),("7453.T","良品計画"),("7459.T","メディパルHD"),
    ("7518.T","ネットワンシステムズ"),("7532.T","パン・パシフィック・インターナショナルHD"),
    ("7550.T","ゼンショーHD"),("7564.T","ワークマン"),("7599.T","IDOM"),
    ("7649.T","スギHD"),("7701.T","島津製作所"),("7716.T","ナカニシ"),
    ("7729.T","東京精密"),("7733.T","オリンパス"),("7735.T","SCREENホールディングス"),
    ("7741.T","HOYA"),("7744.T","ノーリツ鋼機"),("7747.T","朝日インテック"),
    ("7751.T","キヤノン"),("7762.T","シチズン時計"),("7826.T","フルヤ金属"),
    ("7832.T","バンダイナムコHD"),("7846.T","パイロットコーポレーション"),
    ("7912.T","大日本印刷"),("7936.T","アシックス"),("7944.T","ローランド"),
    ("7951.T","ヤマハ"),("7974.T","任天堂"),("7988.T","ニフコ"),
    ("8001.T","伊藤忠商事"),("8002.T","丸紅"),("8015.T","豊田通商"),
    ("8020.T","兼松"),("8031.T","三井物産"),("8035.T","東京エレクトロン"),
    ("8053.T","住友商事"),("8056.T","BIPROGY"),("8058.T","三菱商事"),
    ("8060.T","キヤノンMJ"),("8078.T","阪和興業"),("8088.T","岩谷産業"),
    ("8098.T","稲畑産業"),("8111.T","ゴールドウイン"),("8113.T","ユニ・チャーム"),
    ("8133.T","伊藤忠エネクス"),("8136.T","サンリオ"),("8154.T","加賀電子"),
    ("8174.T","日本瓦斯"),("8194.T","ライフコーポレーション"),("8227.T","しまむら"),
    ("8252.T","丸井グループ"),("8253.T","クレディセゾン"),("8279.T","ヤオコー"),
    ("8306.T","三菱UFJ FG"),("8308.T","りそなHD"),("8309.T","三井住友トラストHD"),
    ("8316.T","三井住友FG"),("8331.T","千葉銀行"),("8354.T","ふくおかFG"),
    ("8410.T","セブン銀行"),("8411.T","みずほFG"),("8424.T","芙蓉総合リース"),
    ("8425.T","みずほリース"),("8439.T","東京センチュリー"),("8473.T","SBIホールディングス"),
    ("8570.T","イオンフィナンシャルS"),("8572.T","アコム"),("8584.T","ジャックス"),
    ("8591.T","オリックス"),("8593.T","三菱HCキャピタル"),("8601.T","大和証券G本社"),
    ("8604.T","野村HD"),("8630.T","SOMPOホールディングス"),("8697.T","日本取引所グループ"),
    ("8698.T","マネックスグループ"),("8725.T","MS&ADインシュアランスGHD"),
    ("8750.T","第一生命HD"),("8766.T","東京海上HD"),("8801.T","三井不動産"),
    ("8802.T","三菱地所"),("8804.T","東京建物"),("8830.T","住友不動産"),
    ("8850.T","スターツコーポレーション"),("8890.T","レーサム"),("8919.T","カチタス"),
    ("9006.T","京浜急行電鉄"),("9007.T","小田急電鉄"),("9022.T","東海旅客鉄道"),
    ("9024.T","西武HD"),("9041.T","近鉄グループHD"),("9064.T","ヤマトHD"),
    ("9065.T","山九"),("9069.T","センコーグループHD"),("9090.T","AZ-COM丸和HD"),
    ("9101.T","日本郵船"),("9104.T","商船三井"),("9107.T","川崎汽船"),
    ("9110.T","NSユナイテッド海運"),("9119.T","飯野海運"),("9143.T","SGホールディングス"),
    ("9147.T","NIPPON EXPRESSホールディングス"),("9302.T","三井倉庫HD"),
    ("9418.T","U-NEXT HOLDINGS"),("9432.T","NTT"),("9433.T","KDDI"),
    ("9434.T","ソフトバンク"),("9435.T","光通信"),("9449.T","GMOインターネットグループ"),
    ("9502.T","中部電力"),("9503.T","関西電力"),("9508.T","九州電力"),
    ("9513.T","電源開発"),("9531.T","東京瓦斯"),("9532.T","大阪瓦斯"),
    ("9602.T","東宝"),("9613.T","NTTデータグループ"),("9684.T","スクウェア・エニックスHD"),
    ("9697.T","カプコン"),("9715.T","トランス・コスモス"),("9719.T","SCSK"),
    ("9735.T","セコム"),("9744.T","メイテックグループHD"),("9759.T","NSD"),
    ("9766.T","コナミグループ"),("9787.T","イオンディライト"),("9843.T","ニトリHD"),
    ("9962.T","ミスミグループ本社"),("9983.T","ファーストリテイリング"),
    ("9984.T","ソフトバンクグループ"),("9989.T","サンドラッグ"),
]

def calc_ma(prices, n):
    if len(prices) < n:
        return None
    return sum(prices[-n:]) / n

def analyze(prices, volumes=None):
    """
    向川式 波乗りトレード ロジック
    MA5/10/20/50/100/200 の上昇パーフェクトオーダーと押し目で判断
    利用可能なデータ量に応じてMAを自動選択
    """
    if not prices or len(prices) < 12:
        return None

    close = prices[-1]
    prev  = prices[:-1]

    # 利用可能なMA期間を決定（データ量に応じて）
    all_periods = [5, 10, 20, 50, 100, 200]
    avail = [p for p in all_periods if len(prices) >= p + 2]

    mas, mas_p, slopes = {}, {}, {}
    for p in avail:
        mas[p]   = calc_ma(prices, p)
        mas_p[p] = calc_ma(prev, p)
        slopes[p] = round(mas[p] - mas_p[p], 1) if mas[p] and mas_p[p] else 0

    if 5 not in mas or 10 not in mas:
        return None

    # ゴールデンクロス（MA5 が MA10 を上抜け）
    gc_today  = (mas_p.get(5, 0) <= mas_p.get(10, 1e9)) and (mas[5] > mas[10])
    ma5_above = mas[5] > mas[10]

    # パーフェクトオーダー確認（MA5>MA10>MA20>MA50>MA100>MA200）
    order_pairs = [(a, b) for a, b in [(5,10),(10,20),(20,50),(50,100),(100,200)]
                   if a in avail and b in avail]
    order_flags  = [mas[a] > mas[b] for a, b in order_pairs]
    aligned_count = sum(order_flags)
    perfect_order = bool(order_flags) and all(order_flags)
    max_pairs     = len(order_pairs)

    # 全MA上昇確認
    rising_flags = [slopes[p] > 0 for p in avail]
    rising_count = sum(rising_flags)

    # 株価 vs 主要MA
    above_ma200 = (close > mas[200]) if 200 in avail else None
    above_ma50  = (close > mas[50])  if 50  in avail else None

    # 押し目検知（株価がMAの ±2% 以内）
    pullback_ma = None
    for p in [5, 10, 20, 50]:
        if p in avail:
            mv = mas[p]
            if mv * 0.98 <= close <= mv * 1.02:
                pullback_ma = f"MA{p}"
                break

    # diff_pct（MA5 vs MA10 乖離率）
    diff_pct = (mas[5] - mas[10]) / mas[10] * 100

    # 出来高確認（直近20日平均の1.5倍以上）
    vol_ratio = None
    vol_confirmed = False
    if volumes and len(volumes) >= 21:
        vol_avg20 = sum(volumes[-21:-1]) / 20
        if vol_avg20 > 0:
            vol_ratio     = round(volumes[-1] / vol_avg20, 2)
            vol_confirmed = vol_ratio >= 1.5

    # スコアリング（向川式 MA配列ベース）
    score = 0
    score += aligned_count * 10           # MA整列ボーナス（最大50点）
    score += rising_count  * 3            # MA上昇ボーナス（最大18点）
    if above_ma200:                score += 10   # MA200より上（長期強気）
    if above_ma50:                 score += 5    # MA50より上
    if pullback_ma and aligned_count >= 3: score += 15  # 押し目チャンス
    if gc_today and aligned_count >= 2:   score += 10  # GC（配列前提）
    if vol_confirmed:              score += 10   # 出来高急増

    # ランキング（向川式）
    # GC は「整列が整った状態でのクロス」のみ本物と判定
    if gc_today and aligned_count >= 3:
        rank = "GC"
    elif score >= 80:
        rank = "S"
    elif score >= 60:
        rank = "A"
    elif score >= 40:
        rank = "B"
    else:
        rank = "C"

    return {
        "close":          round(close, 1),
        "ma5":            round(mas[5], 1),
        "ma10":           round(mas[10], 1),
        "ma20":           round(mas.get(20, 0), 1),
        "ma50":           round(mas.get(50, 0), 1),
        "ma100":          round(mas.get(100, 0), 1),
        "ma200":          round(mas.get(200, 0), 1),
        "diff_pct":       round(diff_pct, 2),
        "gc_today":       gc_today,
        "ma5_above":      ma5_above,
        "perfect_order":  perfect_order,
        "aligned_count":  aligned_count,
        "max_pairs":      max_pairs,
        "rising_count":   rising_count,
        "above_ma200":    above_ma200,
        "above_ma50":     above_ma50,
        "pullback_ma":    pullback_ma,
        "score":          score,
        "rank":           rank,
        "ma5_slope":      slopes.get(5, 0),
        "ma10_slope":     slopes.get(10, 0),
        "ma20_slope":     slopes.get(20, 0),
        "ma50_slope":     slopes.get(50, 0),
        "vol_ratio":      vol_ratio,
        "vol_confirmed":  vol_confirmed,
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

def check_market_regime(index_code="^N225"):
    """市場全体のトレンドを確認（MA20 vs MA50）"""
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
            "ma20": round(ma20, 1),
            "ma50": round(ma50, 1),
            "index": index_code,
            "detail": "上昇トレンド" if bullish else "⚠ 下降トレンド",
        }
    except Exception as e:
        print(f"  市場トレンド取得失敗: {e}")
        return {"bullish": True, "detail": "取得失敗"}

def scan_all(timeframe, weekly_lookup: dict | None = None, market_regime: dict | None = None):
    """全銘柄をスキャンして結果リストを返す"""
    cfg = {
        "1d":  {"period": "1y",   "interval": "1d"},   # MA200に必要な約252日
        "1wk": {"period": "5y",   "interval": "1wk"},  # MA200週足に必要な約260週
        "1mo": {"period": "10y",  "interval": "1mo"},  # MA100月足まで対応
    }[timeframe]

    results = []
    total = len(TICKERS)
    for i, (code, name) in enumerate(TICKERS):
        print(f"  [{i+1:3}/{total}] {code} {name}", end=" ")

        if timeframe == "1d":
            closes, volumes = fetch_ohlcv(code, cfg["period"], cfg["interval"])
        else:
            closes = fetch_closes(code, cfg["period"], cfg["interval"])
            volumes = None

        if closes is None:
            print("SKIP")
            time.sleep(0.3)
            continue

        sig = analyze(closes, volumes)
        if sig:
            # 週足整合フィルター：週足でも MA5 > MA10 なら +15点
            weekly_aligned = weekly_lookup.get(code, False) if weekly_lookup else None
            if weekly_aligned and not sig["gc_today"]:
                sig["score"] += 15
                sig["rank"] = (
                    "S" if sig["score"] >= 75 else
                    "A" if sig["score"] >= 50 else
                    "B" if sig["score"] >= 30 else "C"
                )
            sig["weekly_aligned"] = weekly_aligned

            # 相場全体フィルター：指数が下降トレンドの場合、スコアを減点
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
        time.sleep(0.3)  # レート制限対策

    return results

def main():
    os.makedirs("results", exist_ok=True)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    now_str = now.strftime("%Y-%m-%d %H:%M JST")

    output = {
        "generated_at": now_str,
        "market": "JPX400",
        "timeframes": {}
    }

    # 相場全体トレンド確認（日経225 MA20 vs MA50）
    print(f"\n{'='*50}")
    print(f"相場トレンド確認中...")
    print(f"{'='*50}")
    regime = check_market_regime("^N225")
    print(f"  日経225: MA20={regime['ma20']} / MA50={regime['ma50']} → {regime['detail']}")
    output["market_regime"] = regime

    # 週足を先にスキャンして lookup を構築（日足の週足整合フィルターに使用）
    print(f"\n{'='*50}")
    print(f"JPX400 週足スキャン開始 ({now_str})")
    print(f"{'='*50}")
    wk_results = scan_all("1wk")
    # 週足でも2ペア以上整列（MA5>MA10>MA20）していれば週足整合と判定
    weekly_lookup = {r["code"]: r.get("aligned_count", 0) >= 2 for r in wk_results}
    output["timeframes"]["1wk"] = wk_results

    for tf in ["1d", "1mo"]:
        print(f"\n{'='*50}")
        print(f"JPX400 スキャン開始: {tf} ({now_str})")
        print(f"{'='*50}")
        results = scan_all(
            tf,
            weekly_lookup=weekly_lookup if tf == "1d" else None,
            market_regime=regime if tf == "1d" else None,
        )
        output["timeframes"][tf] = results

        gc   = [r for r in results if r["gc_today"]]
        rank_s = [r for r in results if r["rank"] == "S"]
        wa   = [r for r in results if r.get("weekly_aligned")]
        vol  = [r for r in results if r.get("vol_confirmed")]
        print(f"\n  GC本日: {len(gc)}件  Sランク: {len(rank_s)}件  週足整合: {len(wa)}件  出来高急増: {len(vol)}件  合計: {len(results)}件")

    with open("results/jpx400.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ results/jpx400.json 保存完了")

    # ★追加：時系列データとシグナルを蓄積
    from data_accumulator import append_all
    append_all("JPX400", output)

if __name__ == "__main__":
    main()
