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

def analyze(prices):
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

    diff_t0  = ma5_t0 - ma10_t0
    diff_t1  = ma5_t1 - ma10_t1
    diff_t2  = ma5_t2 - ma10_t2
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

    score = 0
    abs_pct = abs(diff_pct)
    if   abs_pct <= 0.3: score += 40
    elif abs_pct <= 0.7: score += 32
    elif abs_pct <= 1.5: score += 22
    elif abs_pct <= 3.0: score += 12
    elif abs_pct <= 5.0: score += 5
    if is_conv:    score += 15
    if is_accel:   score += 15
    if ma5_rising: score += 15
    if ma5_faster: score += 15
    if gc_today:   score = 0

    rank = "GC" if gc_today else "S" if score >= 75 else "A" if score >= 50 else "B" if score >= 30 else "C"

    return {
        "close":      round(prices[-1], 2),
        "ma5":        round(ma5_t0, 2),
        "ma10":       round(ma10_t0, 2),
        "diff_pct":   round(diff_pct, 2),
        "gc_today":   gc_today,
        "ma5_above":  ma5_above,
        "is_conv":    is_conv,
        "is_accel":   is_accel,
        "ma5_rising": ma5_rising,
        "ma5_faster": ma5_faster,
        "est_days":   est_days,
        "score":      score,
        "rank":       rank,
        "ma5_slope":  round(ma5_slope, 2),
        "ma10_slope": round(ma10_slope, 2),
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

def scan_all(timeframe):
    cfg = {
        "1d":  {"period": "3mo",  "interval": "1d"},
        "1wk": {"period": "2y",   "interval": "1wk"},
        "1mo": {"period": "5y",   "interval": "1mo"},
    }[timeframe]

    results = []
    total = len(SP500_TICKERS)
    for i, (code, name) in enumerate(SP500_TICKERS):
        print(f"  [{i+1:3}/{total}] {code} {name}", end=" ")
        closes = fetch_closes(code, cfg["period"], cfg["interval"])
        if closes is None:
            print("SKIP")
            time.sleep(0.3)
            continue
        sig = analyze(closes)
        if sig:
            results.append({"code": code, "name": name, **sig})
            print(f"rank={sig['rank']} gc={sig['gc_today']} score={sig['score']}")
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

    for tf in ["1d", "1wk", "1mo"]:
        print(f"\n{'='*50}")
        print(f"S&P500 スキャン開始: {tf} ({now_str})")
        print(f"{'='*50}")
        results = scan_all(tf)
        output["timeframes"][tf] = results
        gc     = [r for r in results if r["gc_today"]]
        rank_s = [r for r in results if r["rank"] == "S"]
        print(f"\n  GC本日: {len(gc)}件  Sランク: {len(rank_s)}件  合計: {len(results)}件")

    with open("results/sp500.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ results/sp500.json 保存完了")

if __name__ == "__main__":
    main()
