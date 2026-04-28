"""
S&P500 ゴールデンクロス スキャナー
日足・週足・月足の MA5/MA10 を計算し results/sp500.json に出力
"""
import yfinance as yf
import pandas as pd
import json
import datetime
import time
import os

SP500_TICKERS = [
    ("NVDA","NVIDIA"),("AAPL","Apple"),("GOOGL","Alphabet (A)"),("GOOG","Alphabet (C)"),
    ("MSFT","Microsoft"),("AMZN","Amazon"),("AVGO","Broadcom"),("META","Meta Platforms"),
    ("TSLA","Tesla"),("BRK.B","Berkshire Hathaway"),("WMT","Walmart"),("LLY","Eli Lilly"),
    ("JPM","JPMorgan Chase"),("XOM","Exxon Mobil"),("V","Visa"),("JNJ","Johnson & Johnson"),
    ("MU","Micron Technology"),("MA","Mastercard"),("ORCL","Oracle"),("COST","Costco"),
    ("CVX","Chevron"),("NFLX","Netflix"),("PLTR","Palantir"),("ABBV","AbbVie"),
    ("BAC","Bank of America"),("PG","Procter & Gamble"),("AMD","AMD"),("HD","Home Depot"),
    ("CAT","Caterpillar"),("KO","Coca-Cola"),("CSCO","Cisco Systems"),("GE","GE Aerospace"),
    ("LRCX","Lam Research"),("AMAT","Applied Materials"),("MRK","Merck"),("RTX","RTX Corporation"),
    ("MS","Morgan Stanley"),("PM","Philip Morris"),("GS","Goldman Sachs"),
    ("UNH","UnitedHealth Group"),("WFC","Wells Fargo"),("GEV","GE Vernova"),("IBM","IBM"),
    ("TMUS","T-Mobile US"),("LIN","Linde"),("INTC","Intel"),("MCD","McDonald's"),
    ("VZ","Verizon"),("AXP","American Express"),("PEP","PepsiCo"),("T","AT&T"),
    ("KLAC","KLA Corporation"),("C","Citigroup"),("AMGN","Amgen"),("NEE","NextEra Energy"),
    ("ABT","Abbott Laboratories"),("CRM","Salesforce"),("TMO","Thermo Fisher"),
    ("DIS","Walt Disney"),("TJX","TJX Companies"),("TXN","Texas Instruments"),
    ("ANET","Arista Networks"),("ISRG","Intuitive Surgical"),("GILD","Gilead Sciences"),
    ("SCHW","Charles Schwab"),("APH","Amphenol"),("BA","Boeing"),("COP","ConocoPhillips"),
    ("APP","AppLovin"),("UBER","Uber Technologies"),("DE","Deere & Company"),
    ("ADI","Analog Devices"),("BLK","BlackRock"),("PFE","Pfizer"),("LMT","Lockheed Martin"),
    ("HON","Honeywell"),("UNP","Union Pacific"),("ETN","Eaton Corporation"),
    ("BKNG","Booking Holdings"),("QCOM","Qualcomm"),("WELL","Welltower"),("DHR","Danaher"),
    ("PANW","Palo Alto Networks"),("LOW","Lowe's"),("SPGI","S&P Global"),("CB","Chubb"),
    ("SYK","Stryker"),("INTU","Intuit"),("ACN","Accenture"),("PLD","Prologis"),
    ("PGR","Progressive"),("BMY","Bristol-Myers Squibb"),("NOW","ServiceNow"),
    ("PH","Parker-Hannifin"),("COF","Capital One"),("VRTX","Vertex Pharmaceuticals"),
    ("GLW","Corning"),("MDT","Medtronic"),("HCA","HCA Healthcare"),("CME","CME Group"),
    ("MCK","McKesson"),("MO","Altria Group"),("NEM","Newmont"),("SBUX","Starbucks"),
    ("CEG","Constellation Energy"),("SO","Southern Company"),("CRWD","CrowdStrike"),
    ("DELL","Dell Technologies"),("CMCSA","Comcast"),("BSX","Boston Scientific"),
    ("ADBE","Adobe"),("DUK","Duke Energy"),("NOC","Northrop Grumman"),("HWM","Howmet Aerospace"),
    ("NRG","NRG Energy"),("EQIX","Equinix"),("TT","Trane Technologies"),
    ("GD","General Dynamics"),("WM","Waste Management"),("WMB","Williams Companies"),
    ("CVS","CVS Health"),("ICE","Intercontinental Exchange"),("MAR","Marriott International"),
    ("FDX","FedEx"),("PWR","Quanta Services"),("ADP","Automatic Data Processing"),
    ("SNPS","Synopsys"),("UPS","United Parcel Service"),("PNC","PNC Financial"),
    ("BX","Blackstone"),("AMT","American Tower"),("JCI","Johnson Controls"),
    ("KKR","KKR & Co."),("ABNB","Airbnb"),("USB","U.S. Bancorp"),
    ("CDNS","Cadence Design Systems"),("BK","Bank of New York Mellon"),
    ("FCX","Freeport-McMoRan"),("MCO","Moody's"),("NKE","Nike"),("SHW","Sherwin-Williams"),
    ("REGN","Regeneron"),("MMM","3M Company"),("ITW","Illinois Tool Works"),
    ("MSI","Motorola Solutions"),("CMI","Cummins"),("EOG","EOG Resources"),
    ("RCL","Royal Caribbean"),("KMI","Kinder Morgan"),("ORLY","O'Reilly Automotive"),
    ("ECL","Ecolab"),("EMR","Emerson Electric"),("SLB","SLB N.V."),
    ("MDLZ","Mondelez International"),("CTAS","Cintas"),("MNST","Monster Beverage"),
    ("CSX","CSX Corporation"),("PSX","Phillips 66"),("VLO","Valero Energy"),("AON","Aon"),
    ("DASH","DoorDash"),("CRH","CRH plc"),("HLT","Hilton Worldwide"),("ROST","Ross Stores"),
    ("MPC","Marathon Petroleum"),("CI","Cigna Group"),("GM","General Motors"),
    ("AEP","American Electric Power"),("CL","Colgate-Palmolive"),("RSG","Republic Services"),
    ("TDG","TransDigm Group"),("LHX","L3Harris Technologies"),("HOOD","Robinhood Markets"),
    ("APO","Apollo Global Management"),("NSC","Norfolk Southern"),("TRV","Travelers Companies"),
    ("ELV","Elevance Health"),("COR","Cencora"),("APD","Air Products"),("BKR","Baker Hughes"),
    ("FTNT","Fortinet"),("SRE","Sempra"),("DLR","Digital Realty Trust"),("PCAR","PACCAR"),
    ("SPG","Simon Property Group"),("OXY","Occidental Petroleum"),("TEL","TE Connectivity"),
    ("O","Realty Income"),("OKE","ONEOK"),("TFC","Truist Financial"),
    ("AJG","Arthur J. Gallagher"),("AZO","AutoZone"),("AFL","Aflac"),
    ("FANG","Diamondback Energy"),("ALL","Allstate"),("COIN","Coinbase"),
    ("MPWR","Monolithic Power Systems"),("CTVA","Corteva"),("ADSK","Autodesk"),
    ("D","Dominion Energy"),("TGT","Target"),("TRGP","Targa Resources"),
    ("VST","Vistra Corp."),("FAST","Fastenal"),("GWW","W.W. Grainger"),
    ("EA","Electronic Arts"),("KEYS","Keysight Technologies"),("NXPI","NXP Semiconductors"),
    ("CARR","Carrier Global"),("NDAQ","Nasdaq Inc."),("AME","AMETEK"),("ZTS","Zoetis"),
    ("CAH","Cardinal Health"),("EXC","Exelon"),("XEL","Xcel Energy"),("PSA","Public Storage"),
    ("EW","Edwards Lifesciences"),("F","Ford Motor"),("URI","United Rentals"),
    ("IDXX","IDEXX Laboratories"),("ETR","Entergy"),("GRMN","Garmin"),("DDOG","Datadog"),
    ("MET","MetLife"),("BDX","Becton Dickinson"),("KR","Kroger"),("YUM","Yum! Brands"),
    ("HSY","Hershey"),("CMG","Chipotle Mexican Grill"),("CVNA","Carvana"),
    ("DAL","Delta Air Lines"),("PYPL","PayPal"),("WAB","Westinghouse Air Brake"),
    ("FITB","Fifth Third Bancorp"),("EQT","EQT Corporation"),("MSCI","MSCI Inc."),
    ("AMP","Ameriprise Financial"),("CBRE","CBRE Group"),("EBAY","eBay"),
    ("ROK","Rockwell Automation"),("DHI","D.R. Horton"),("AXON","Axon Enterprise"),
    ("GEHC","GE HealthCare"),("HIG","Hartford Financial"),("VICI","VICI Properties"),
    ("IRM","Iron Mountain"),("TROW","T. Rowe Price"),("OTIS","Otis Worldwide"),
    ("NUE","Nucor"),("FIS","Fidelity National Info"),("HBAN","Huntington Bancshares"),
    ("PPG","PPG Industries"),("MTB","M&T Bank"),("RF","Regions Financial"),
    ("STT","State Street"),("IQV","IQVIA Holdings"),("GIS","General Mills"),
    ("EFX","Equifax"),("SYY","Sysco"),("HAL","Halliburton"),("CTSH","Cognizant Technology"),
    ("DOW","Dow Inc."),("DD","DuPont"),("LEN","Lennar"),("ZBH","Zimmer Biomet"),
    ("HES","Hess Corporation"),("AIG","American International Group"),
    ("TTWO","Take-Two Interactive"),("NTRS","Northern Trust"),("BIIB","Biogen"),
    ("BRO","Brown & Brown"),("DOV","Dover Corporation"),("RMD","ResMed"),
    ("LYB","LyondellBasell"),("PPL","PPL Corporation"),("FTV","Fortive"),
    ("ACGL","Arch Capital Group"),("PKG","Packaging Corp of America"),
    ("AWK","American Water Works"),("LDOS","Leidos Holdings"),("ANSS","ANSYS"),
    ("TYL","Tyler Technologies"),("WAT","Waters Corporation"),("BR","Broadridge Financial"),
    ("MOH","Molina Healthcare"),("CLX","Clorox"),("CBOE","Cboe Global Markets"),
    ("HOLX","Hologic"),("DRI","Darden Restaurants"),("DGX","Quest Diagnostics"),
    ("CINF","Cincinnati Financial"),("RJF","Raymond James Financial"),
    ("GPN","Global Payments"),("HPE","Hewlett Packard Enterprise"),("NVR","NVR Inc."),
    ("ERIE","Erie Indemnity"),("ZBRA","Zebra Technologies"),("CFG","Citizens Financial"),
    ("SNA","Snap-on"),("EXPE","Expedia Group"),("MKC","McCormick & Company"),
    ("IFF","International Flavors"),("RL","Ralph Lauren"),("WRB","W.R. Berkley"),
    ("ALB","Albemarle"),("MAS","Masco Corporation"),("TRMB","Trimble Inc."),
    ("ALLE","Allegion"),("IPG","Interpublic Group"),("OMC","Omnicom Group"),
    ("HST","Host Hotels & Resorts"),("KIM","Kimco Realty"),("AVB","AvalonBay Communities"),
    ("EQR","Equity Residential"),("MAA","Mid-America Apartment"),("AIZ","Assurant"),
    ("L","Loews Corporation"),("PRU","Prudential Financial"),("KHC","Kraft Heinz"),
    ("CAG","Conagra Brands"),("CPB","Campbell Soup"),("PCG","PG&E Corporation"),
    ("AES","AES Corporation"),("CMS","CMS Energy"),("LNT","Alliant Energy"),
    ("EVRG","Evergy"),("NI","NiSource"),("ES","Eversource Energy"),
    ("WEC","WEC Energy Group"),("CNP","CenterPoint Energy"),("FE","FirstEnergy"),
    ("DTE","DTE Energy"),("ATO","Atmos Energy"),("EIX","Edison International"),
    ("SWK","Stanley Black & Decker"),("PNR","Pentair"),("GNRC","Generac Holdings"),
    ("IR","Ingersoll Rand"),("XYL","Xylem"),("GGG","Graco Inc."),
    ("IEX","IDEX Corporation"),("FSLR","First Solar"),("ENPH","Enphase Energy"),
    ("AEE","Ameren Corporation"),("ARE","Alexandria Real Estate"),("VTR","Ventas"),
    ("SUI","Sun Communities"),("AMH","American Homes 4 Rent"),("INVH","Invitation Homes"),
    ("REXR","Rexford Industrial Realty"),("EGP","EastGroup Properties"),
    ("JKHY","Jack Henry & Associates"),("FFIV","F5 Inc."),("ALGN","Align Technology"),
    ("TFX","Teleflex"),("TECH","Bio-Techne"),("CPAY","Corpay"),
    ("FNF","Fidelity National Financial"),("LPLA","LPL Financial"),("SSNC","SS&C Technologies"),
    ("EG","Everest Group"),("RGA","Reinsurance Group"),("DVN","Devon Energy"),
    ("MRO","Marathon Oil"),("APA","APA Corporation"),("CTRA","Coterra Energy"),
    ("NCLH","Norwegian Cruise Line"),("CCL","Carnival Corporation"),("UAL","United Airlines"),
    ("AAL","American Airlines"),("LUV","Southwest Airlines"),("ALK","Alaska Air Group"),
    ("DKNG","DraftKings"),("MGM","MGM Resorts"),("WYNN","Wynn Resorts"),
    ("CZR","Caesars Entertainment"),("STLD","Steel Dynamics"),
    ("RS","Reliance Steel & Aluminum"),("AMCR","Amcor"),("SEE","Sealed Air"),
    ("CCK","Crown Holdings"),("AOS","A.O. Smith"),("AGCO","AGCO Corporation"),
    ("LII","Lennox International"),("PTC","PTC Inc."),("VRSK","Verisk Analytics"),
    ("BAH","Booz Allen Hamilton"),("EPAM","EPAM Systems"),("MAN","ManpowerGroup"),
    ("CRL","Charles River Laboratories"),("INCY","Incyte Corporation"),
    ("BMRN","BioMarin Pharmaceutical"),("MRNA","Moderna"),("ILMN","Illumina"),
    ("A","Agilent Technologies"),("STE","STERIS plc"),("DXCM","DexCom"),
    ("TDOC","Teladoc Health"),("GL","Globe Life"),("LNC","Lincoln National"),
    ("UDR","UDR Inc."),("CPT","Camden Property Trust"),("ESS","Essex Property Trust"),
    ("REG","Regency Centers"),("HPQ","HP Inc."),("VRSN","VeriSign"),
    ("SWKS","Skyworks Solutions"),("MCHP","Microchip Technology"),
    ("ON","ON Semiconductor"),("STX","Seagate Technology"),("NTAP","NetApp"),
    ("AKAM","Akamai Technologies"),("CDW","CDW Corporation"),("OKTA","Okta"),
    ("SNOW","Snowflake"),("TEAM","Atlassian"),("VEEV","Veeva Systems"),("WDAY","Workday"),
    ("NET","Cloudflare"),("RPM","RPM International"),("CF","CF Industries"),
    ("MOS","Mosaic Company"),("CE","Celanese"),("EMN","Eastman Chemical"),
    ("DKS","Dick's Sporting Goods"),("BURL","Burlington Stores"),("FIVE","Five Below"),
    ("SFM","Sprouts Farmers Market"),("BJ","BJ's Wholesale Club"),
    ("WBD","Warner Bros. Discovery"),("NWSA","News Corp A"),
    ("FOXA","Fox Corporation A"),("FOX","Fox Corporation B"),
]

def calc_ma(prices, n):
    if len(prices) < n:
        return None
    return sum(prices[-n:]) / n

def analyze(prices, volumes=None):
    """
    向川式 波乗りトレード ロジック
    MA5/10/20/50/100/200 の上昇パーフェクトオーダーと押し目で判断
    """
    if not prices or len(prices) < 12:
        return None

    close = prices[-1]
    prev  = prices[:-1]

    all_periods = [5, 10, 20, 50, 100, 200]
    avail = [p for p in all_periods if len(prices) >= p + 2]

    mas, mas_p, slopes = {}, {}, {}
    for p in avail:
        mas[p]   = calc_ma(prices, p)
        mas_p[p] = calc_ma(prev, p)
        slopes[p] = round(mas[p] - mas_p[p], 2) if mas[p] and mas_p[p] else 0

    if 5 not in mas or 10 not in mas:
        return None

    gc_today  = (mas_p.get(5, 0) <= mas_p.get(10, 1e9)) and (mas[5] > mas[10])
    ma5_above = mas[5] > mas[10]

    order_pairs  = [(a, b) for a, b in [(5,10),(10,20),(20,50),(50,100),(100,200)]
                    if a in avail and b in avail]
    order_flags  = [mas[a] > mas[b] for a, b in order_pairs]
    aligned_count = sum(order_flags)
    perfect_order = bool(order_flags) and all(order_flags)
    max_pairs     = len(order_pairs)

    rising_flags = [slopes[p] > 0 for p in avail]
    rising_count = sum(rising_flags)

    above_ma200 = (close > mas[200]) if 200 in avail else None
    above_ma50  = (close > mas[50])  if 50  in avail else None

    pullback_ma = None
    for p in [5, 10, 20, 50]:
        if p in avail:
            mv = mas[p]
            if mv * 0.98 <= close <= mv * 1.02:
                pullback_ma = f"MA{p}"
                break

    diff_pct = (mas[5] - mas[10]) / mas[10] * 100

    vol_ratio = None
    vol_confirmed = False
    if volumes and len(volumes) >= 21:
        vol_avg20 = sum(volumes[-21:-1]) / 20
        if vol_avg20 > 0:
            vol_ratio     = round(volumes[-1] / vol_avg20, 2)
            vol_confirmed = vol_ratio >= 1.5

    score = 0
    score += aligned_count * 10
    score += rising_count  * 3
    if above_ma200:                        score += 10
    if above_ma50:                         score += 5
    if pullback_ma and aligned_count >= 3: score += 15
    if gc_today and aligned_count >= 2:    score += 10
    if vol_confirmed:                      score += 10

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
        "close":          round(close, 2),
        "ma5":            round(mas[5], 2),
        "ma10":           round(mas[10], 2),
        "ma20":           round(mas.get(20, 0), 2),
        "ma50":           round(mas.get(50, 0), 2),
        "ma100":          round(mas.get(100, 0), 2),
        "ma200":          round(mas.get(200, 0), 2),
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

def check_market_regime(index_code="^GSPC"):
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
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "index": index_code,
            "detail": "上昇トレンド" if bullish else "⚠ 下降トレンド",
        }
    except Exception as e:
        print(f"  市場トレンド取得失敗: {e}")
        return {"bullish": True, "detail": "取得失敗"}

def scan_all(timeframe, weekly_lookup: dict | None = None, market_regime: dict | None = None):
    cfg = {
        "1d":  {"period": "1y",   "interval": "1d"},
        "1wk": {"period": "5y",   "interval": "1wk"},
        "1mo": {"period": "10y",  "interval": "1mo"},
    }[timeframe]

    results = []
    total = len(SP500_TICKERS)
    for i, (code, name) in enumerate(SP500_TICKERS):
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
        time.sleep(0.3)
    return results

def main():
    os.makedirs("results", exist_ok=True)
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    now_str = now.strftime("%Y-%m-%d %H:%M JST")

    output = {
        "generated_at": now_str,
        "market": "S&P500",
        "timeframes": {}
    }

    # 相場全体トレンド確認（S&P500 MA20 vs MA50）
    print(f"\n{'='*50}")
    print(f"相場トレンド確認中...")
    print(f"{'='*50}")
    regime = check_market_regime("^GSPC")
    print(f"  S&P500: MA20={regime['ma20']} / MA50={regime['ma50']} → {regime['detail']}")
    output["market_regime"] = regime

    # 週足を先にスキャンして lookup を構築（日足の週足整合フィルターに使用）
    print(f"\n{'='*50}")
    print(f"S&P500 週足スキャン開始 ({now_str})")
    print(f"{'='*50}")
    wk_results = scan_all("1wk")
    weekly_lookup = {r["code"]: r.get("aligned_count", 0) >= 2 for r in wk_results}
    output["timeframes"]["1wk"] = wk_results

    for tf in ["1d", "1mo"]:
        print(f"\n{'='*50}")
        print(f"S&P500 スキャン開始: {tf} ({now_str})")
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

    with open("results/sp500.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ results/sp500.json 保存完了")

    # ★追加：時系列データとシグナルを蓄積
    from data_accumulator import append_all
    append_all("SP500", output)

if __name__ == "__main__":
    main()
