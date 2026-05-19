"""
波乗りトレード v3.2 — 売却タイミング アラートメール
定義書 v3.2 の売却条件を毎日チェックし NOTIFY_EMAIL へ送信する。

【波乗り層（short）チェック項目】
 A. 損切り① SMA(20)を1%以上下抜け
 B. 損切り② エントリー価格 -7%
 C. 損切り③ PO崩壊（SMA5 < SMA10）[US株は3連続日]
 D. BE到達  含み益 +10% → 建値ストップ移動を推奨
 E. トレーリング BE発動後に SMA(10)割れ
 F. 半利確   RSI過熱（大型株:80超 / 中型株:72〜75超）

【長期保有層（long）チェック項目】
 G. 部分利確① 日足RSI≥70 かつ SMA(20)乖離≥+15% → 15%利確
 H. 部分利確② 週足RSI≥70 かつ 週足SMA(13w)乖離≥+25% → 20%利確
 I. 部分利確③ 長大上ヒゲ（上ヒゲ比率≥50%）かつ 出来高≥2倍 → 10%利確
 J. 部分利確④ 取得比+50/+100/+200% 節目
 K. 縮小    週足SMA(13w) or SMA(26w)割れ
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Optional

import yfinance as yf
import pandas as pd
import requests


# ═══════════════════════════════════════════════════════
# 定数・閾値
# ═══════════════════════════════════════════════════════
SL_PCT        = 0.07    # 損切り② -7%
SMA20_SL_PCT  = 0.01    # SMA20下抜け判定マージン
BE_TRIGGER    = 0.10    # ブレークイーントリガー +10%
RSI_BIG_CAP   = 80.0    # 超大型株（10兆円超）半利確閾値
RSI_MID_CAP   = 72.0    # 中型株 半利確閾値
BIG_CAP_JPY   = 10_000_000_000_000  # 10兆円

LT_RSI_D_MIN     = 70.0    # 長期①日足RSI
LT_DEV_D_MIN     = 15.0    # 長期①日足SMA20乖離%
LT_RSI_W_MIN     = 70.0    # 長期②週足RSI
LT_DEV_W_MIN     = 25.0    # 長期②週足SMA13乖離%
LT_UPPER_SHADOW  = 0.50    # 長期③上ヒゲ比率（ヒゲ/高低差）
LT_VOL_MULT      = 2.0     # 長期③出来高倍率
VIX_WARN         = 28.0
VIX_HALT         = 35.0

PO_BREAK_DAYS_US = 3        # US株PO連続崩壊日数

PERIOD_D = "3mo"            # 日足データ取得期間
PERIOD_W = "12mo"           # 週足データ取得期間


# ═══════════════════════════════════════════════════════
# ユーティリティ
# ═══════════════════════════════════════════════════════
def _load_dotenv() -> None:
    path = Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs    = avg_g / avg_l.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _is_us(code: str) -> bool:
    return not code.endswith(".T")


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _yen(v: float) -> str:
    return f"¥{v:,.0f}"


def _usd(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_price(v: float, is_us: bool) -> str:
    return _usd(v) if is_us else _yen(v)


# ═══════════════════════════════════════════════════════
# 指標計算
# ═══════════════════════════════════════════════════════
def _calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """日足 DataFrame に各種指標を追加して返す。"""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    for n in [5, 10, 20, 60]:
        df[f"sma{n}"] = df["close"].rolling(n).mean()
    df["rsi14"] = _rsi(df["close"])
    df["vol20"] = df["volume"].rolling(20).mean()
    return df


def _calc_weekly(code: str) -> Optional[pd.DataFrame]:
    """週足 DataFrame に SMA13/26 と RSI14 を追加して返す。"""
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(period=PERIOD_W, interval="1wk")
        if df.empty or len(df) < 14:
            return None
        df.columns = [c.lower() for c in df.columns]
        df["sma13w"] = df["close"].rolling(13).mean()
        df["sma26w"] = df["close"].rolling(26).mean()
        df["rsi14w"] = _rsi(df["close"])
        return df
    except Exception:
        return None


def _po_break_streak(df: pd.DataFrame, lookback: int = 5) -> int:
    """直近 lookback 日中の PO 崩壊連続日数を返す。"""
    streak = 0
    rows = df.tail(lookback)
    for _, row in rows.iloc[::-1].iterrows():
        if row.get("sma5", float("nan")) < row.get("sma10", float("nan")):
            streak += 1
        else:
            break
    return streak


# ═══════════════════════════════════════════════════════
# アラート判定
# ═══════════════════════════════════════════════════════
class Alert:
    def __init__(self, level: str, code: str, name: str, message: str,
                 action: str, detail: str = ""):
        self.level   = level    # "CRITICAL" / "WARN" / "INFO"
        self.code    = code
        self.name    = name
        self.message = message
        self.action  = action
        self.detail  = detail

    @property
    def color(self) -> str:
        return {"CRITICAL": "#d93025", "WARN": "#f5a623", "INFO": "#1a3a6b"}[self.level]

    @property
    def icon(self) -> str:
        return {"CRITICAL": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}[self.level]


def check_short(pos: dict, df: pd.DataFrame) -> list[Alert]:
    """波乗り層の売却条件チェック。"""
    alerts: list[Alert] = []
    if len(df) < 21:
        return alerts

    row   = df.iloc[-1]
    code  = pos["code"]
    name  = pos["name"]
    close = float(row["close"])
    sma5  = float(row.get("sma5",  float("nan")))
    sma10 = float(row.get("sma10", float("nan")))
    sma20 = float(row.get("sma20", float("nan")))
    rsi   = float(row.get("rsi14", float("nan")))
    entry = float(pos["entry_price"])
    mc    = pos.get("market_cap_jpy", 0)
    be_ok = pos.get("be_triggered", False)
    is_us = _is_us(code)
    pnl_pct = (close - entry) / entry * 100

    # A. SMA20 下抜け
    if not pd.isna(sma20) and close < sma20 * (1 - SMA20_SL_PCT):
        alerts.append(Alert(
            "CRITICAL", code, name,
            f"損切り①：SMA(20)を {SMA20_SL_PCT*100:.0f}%以上下抜け",
            "本日引けまたは翌日寄りに損切り",
            f"終値 {_fmt_price(close, is_us)} / SMA20 {_fmt_price(sma20, is_us)} "
            f"（乖離 {(close/sma20-1)*100:+.2f}%）",
        ))

    # B. 価格損切り -7%
    if pnl_pct <= -SL_PCT * 100:
        alerts.append(Alert(
            "CRITICAL", code, name,
            f"損切り②：エントリー比 {_pct(pnl_pct)}",
            "即時損切り（-7%ルール）",
            f"エントリー {_fmt_price(entry, is_us)} → 現在 {_fmt_price(close, is_us)}",
        ))

    # C. PO 崩壊
    if not pd.isna(sma5) and not pd.isna(sma10):
        streak = _po_break_streak(df)
        threshold = PO_BREAK_DAYS_US if is_us else 1
        if streak >= threshold:
            alerts.append(Alert(
                "CRITICAL" if (not is_us or streak >= PO_BREAK_DAYS_US) else "WARN",
                code, name,
                f"損切り③：PO崩壊 {streak}営業日継続（SMA5 < SMA10）",
                "翌日寄りに売却",
                f"SMA5 {_fmt_price(sma5, is_us)} / SMA10 {_fmt_price(sma10, is_us)}",
            ))

    # D. ブレークイーン到達（+10%）
    if not be_ok and pnl_pct >= BE_TRIGGER * 100:
        alerts.append(Alert(
            "INFO", code, name,
            f"BE到達：含み益 {_pct(pnl_pct)} → 建値ストップへの移動を推奨",
            "逆指値をエントリー価格に移動",
            f"現在値 {_fmt_price(close, is_us)}（positions.json の be_triggered を true に変更してください）",
        ))

    # E. トレーリング（BE発動後、SMA10割れ）
    if be_ok and not pd.isna(sma10) and close < sma10:
        alerts.append(Alert(
            "WARN", code, name,
            f"トレーリング：SMA(10)割れ（BE発動後）",
            "翌日寄りに売却（利益確定）",
            f"終値 {_fmt_price(close, is_us)} / SMA10 {_fmt_price(sma10, is_us)}",
        ))

    # F. RSI 過熱→半利確
    if not pd.isna(rsi):
        rsi_thresh = RSI_BIG_CAP if mc >= BIG_CAP_JPY else RSI_MID_CAP
        size_label = "超大型株" if mc >= BIG_CAP_JPY else "中型〜大型株"
        if rsi >= rsi_thresh:
            alerts.append(Alert(
                "WARN", code, name,
                f"半利確推奨：RSI {rsi:.1f} 過熱（{size_label}基準 {rsi_thresh:.0f}超）",
                f"保有株数の 50% を部分利確",
                f"現在値 {_fmt_price(close, is_us)}",
            ))

    return alerts


def check_long(pos: dict, df: pd.DataFrame, df_w: Optional[pd.DataFrame]) -> list[Alert]:
    """長期保有層の部分利確条件チェック。"""
    alerts: list[Alert] = []
    if len(df) < 21:
        return alerts

    row      = df.iloc[-1]
    code     = pos["code"]
    name     = pos["name"]
    close    = float(row["close"])
    sma20    = float(row.get("sma20", float("nan")))
    rsi_d    = float(row.get("rsi14", float("nan")))
    vol      = float(row.get("volume", float("nan")))
    vol20    = float(row.get("vol20", float("nan")))
    open_    = float(row.get("open", float("nan")))
    high     = float(row.get("high", float("nan")))
    low      = float(row.get("low", float("nan")))
    avg_cost = float(pos["avg_cost"])
    realized = float(pos.get("realized_pct", 0.0))
    is_us    = _is_us(code)
    gain_pct = (close - avg_cost) / avg_cost * 100

    # 日足SMA20乖離
    dev_d = (close / sma20 - 1) * 100 if not pd.isna(sma20) and sma20 > 0 else float("nan")

    # G. 部分利確①：日足RSI≥70 かつ SMA20乖離≥+15%
    if not pd.isna(rsi_d) and not pd.isna(dev_d):
        if rsi_d >= LT_RSI_D_MIN and dev_d >= LT_DEV_D_MIN:
            alerts.append(Alert(
                "WARN", code, name,
                f"部分利確①：日足 RSI {rsi_d:.1f}≥70 かつ SMA(20)乖離 {dev_d:+.1f}%≥+15%",
                "保有の 15% を部分利確",
                f"現在値 {_fmt_price(close, is_us)}",
            ))

    # H. 部分利確②：週足RSI≥70 かつ 週足SMA13乖離≥+25%
    if df_w is not None and len(df_w) >= 14:
        row_w  = df_w.iloc[-1]
        rsi_w  = float(row_w.get("rsi14w", float("nan")))
        sma13w = float(row_w.get("sma13w", float("nan")))
        dev_w  = (close / sma13w - 1) * 100 if not pd.isna(sma13w) and sma13w > 0 else float("nan")
        if not pd.isna(rsi_w) and not pd.isna(dev_w):
            if rsi_w >= LT_RSI_W_MIN and dev_w >= LT_DEV_W_MIN:
                alerts.append(Alert(
                    "WARN", code, name,
                    f"部分利確②：週足 RSI {rsi_w:.1f}≥70 かつ SMA(13w)乖離 {dev_w:+.1f}%≥+25%",
                    "保有の 20% を部分利確",
                    f"現在値 {_fmt_price(close, is_us)}",
                ))

        # K. 週足SMA割れ（保有縮小）
        sma26w = float(row_w.get("sma26w", float("nan")))
        if not pd.isna(sma13w) and close < sma13w * 0.99:
            alerts.append(Alert(
                "CRITICAL", code, name,
                f"縮小シグナル：週足 SMA(13w) を 1%以上下抜け",
                "保有の 25% を売却",
                f"終値 {_fmt_price(close, is_us)} / 週足SMA13 {_fmt_price(sma13w, is_us)}",
            ))
        elif not pd.isna(sma26w) and close < sma26w * 0.99:
            alerts.append(Alert(
                "CRITICAL", code, name,
                f"縮小シグナル：週足 SMA(26w) を 1%以上下抜け",
                "さらに保有の 25% を売却",
                f"終値 {_fmt_price(close, is_us)} / 週足SMA26 {_fmt_price(sma26w, is_us)}",
            ))

    # I. 部分利確③：長大上ヒゲ＋異常出来高
    if not any(pd.isna(v) for v in [open_, high, low, close, vol, vol20]):
        hl_range = high - low
        upper_shadow = high - max(open_, close)
        if hl_range > 0 and (upper_shadow / hl_range) >= LT_UPPER_SHADOW:
            if vol >= vol20 * LT_VOL_MULT:
                alerts.append(Alert(
                    "WARN", code, name,
                    f"部分利確③：長大上ヒゲ＋出来高急増（平均{LT_VOL_MULT:.0f}倍超）",
                    "保有の 10% を部分利確",
                    f"上ヒゲ比率 {upper_shadow/hl_range*100:.0f}% / 出来高比 {vol/vol20:.1f}倍",
                ))

    # J. 部分利確④：取得価格基準の節目
    milestones = [(50, 0.15), (100, 0.30), (200, 0.50)]
    for pct_threshold, target_realized in milestones:
        if gain_pct >= pct_threshold and realized < target_realized:
            alerts.append(Alert(
                "INFO", code, name,
                f"部分利確④：平均取得比 +{gain_pct:.1f}% → +{pct_threshold}% 節目",
                f"累計利確が {target_realized*100:.0f}% になるまで追加利確",
                f"現在 realized_pct={realized:.0%} / 目標 {target_realized:.0%}（positions.json を更新してください）",
            ))
            break  # 下から順に最初のトリガーのみ

    return alerts


# ═══════════════════════════════════════════════════════
# 市場環境チェック
# ═══════════════════════════════════════════════════════
def check_market_env() -> dict:
    result = {"topix": None, "spy": None, "vix": None,
              "topix_ok": True, "spy_ok": True,
              "vix_val": None, "vix_label": "", "vix_color": "#00955a"}
    try:
        df_t = yf.Ticker("^TOPX").history(period="3mo")
        if not df_t.empty:
            c = float(df_t["Close"].iloc[-1])
            s = float(df_t["Close"].rolling(20).mean().iloc[-1])
            result["topix"] = c
            result["topix_ok"] = c > s
    except Exception:
        pass
    try:
        df_s = yf.Ticker("SPY").history(period="3mo")
        if not df_s.empty:
            c = float(df_s["Close"].iloc[-1])
            s = float(df_s["Close"].rolling(20).mean().iloc[-1])
            result["spy"] = c
            result["spy_ok"] = c > s
    except Exception:
        pass
    try:
        df_v = yf.Ticker("^VIX").history(period="2d")
        if not df_v.empty:
            v = float(df_v["Close"].iloc[-1])
            result["vix_val"] = v
            if v >= VIX_HALT:
                result["vix_label"] = f"{v:.1f} 危険域（新規停止＋利確検討）"
                result["vix_color"] = "#d93025"
            elif v >= VIX_WARN:
                result["vix_label"] = f"{v:.1f} 警戒域（新規エントリー停止）"
                result["vix_color"] = "#f5a623"
            else:
                result["vix_label"] = f"{v:.1f} 通常域"
                result["vix_color"] = "#00955a"
    except Exception:
        pass
    return result


# ═══════════════════════════════════════════════════════
# HTML メール生成
# ═══════════════════════════════════════════════════════
_CSS = """
body{font-family:'Helvetica Neue',Arial,sans-serif;background:#f4f6f9;margin:0;padding:0;color:#1a1a1a}
.wrap{max-width:700px;margin:20px auto;background:#fff;border-radius:8px;
      box-shadow:0 2px 8px rgba(0,0,0,.1);overflow:hidden}
.header{background:#1a3a6b;color:#fff;padding:20px 28px}
.header h1{margin:0;font-size:20px}
.header p{margin:4px 0 0;font-size:13px;opacity:.8}
.section{padding:20px 28px;border-bottom:1px solid #eee}
.section h2{font-size:15px;color:#1a3a6b;margin:0 0 12px;border-left:4px solid #1a3a6b;padding-left:10px}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;color:#fff}
.badge-crit{background:#d93025}.badge-warn{background:#f5a623}.badge-info{background:#1a3a6b}
.alert-card{border-left:4px solid #ccc;padding:10px 14px;margin:8px 0;border-radius:0 6px 6px 0;background:#fafafa}
.alert-card.crit{border-color:#d93025;background:#fff5f5}
.alert-card.warn{border-color:#f5a623;background:#fffbf0}
.alert-card.info{border-color:#1a3a6b;background:#f0f4ff}
.alert-title{font-weight:bold;font-size:14px;margin:0 0 4px}
.alert-action{color:#00955a;font-size:13px;font-weight:bold;margin:4px 0}
.alert-detail{color:#666;font-size:12px;margin:0}
table.pos{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
table.pos th{background:#e8eef8;color:#1a3a6b;padding:6px 8px;text-align:left;border:1px solid #c8d0e0}
table.pos td{border:1px solid #dee4ec;padding:5px 8px}
table.pos tr:nth-child(even) td{background:#f7f9fc}
.green{color:#00955a}.red{color:#d93025}.orange{color:#f5a623}
.no-alert{color:#999;font-size:13px;padding:8px 0}
.footer{background:#f0f2f8;padding:12px 28px;font-size:11px;color:#888;text-align:center}
"""


def _alert_card_html(a: Alert) -> str:
    cls   = {"CRITICAL": "crit", "WARN": "warn", "INFO": "info"}[a.level]
    badge = {"CRITICAL": "badge-crit", "WARN": "badge-warn", "INFO": "badge-info"}[a.level]
    label = {"CRITICAL": "要注意", "WARN": "警戒", "INFO": "情報"}[a.level]
    return f"""
<div class="alert-card {cls}">
  <p class="alert-title">
    {a.icon} <span class="badge {badge}">{label}</span>
    &nbsp;<strong>{a.name}（{a.code}）</strong>
  </p>
  <p class="alert-action">▶ アクション：{a.action}</p>
  <p class="alert-detail">{a.message}{'　<br><span style="color:#888">'+a.detail+'</span>' if a.detail else ''}</p>
</div>"""


def _market_row(label: str, val, ok: Optional[bool]) -> str:
    if val is None:
        return f"<tr><td>{label}</td><td colspan=2 style='color:#999'>取得失敗</td></tr>"
    status = "通常運用" if ok else "新規エントリー停止"
    color  = "#00955a" if ok else "#d93025"
    return (f"<tr><td>{label}</td>"
            f"<td style='text-align:right'>{val:,.2f}</td>"
            f"<td style='color:{color};font-weight:bold'>{status}</td></tr>")


def build_html(positions: list[dict], all_alerts: list[Alert], env: dict) -> str:
    today = datetime.date.today().strftime("%Y/%m/%d (%a)")

    # --- 市場環境セクション ---
    topix_row = _market_row("TOPIX", env.get("topix"), env.get("topix_ok"))
    spy_row   = _market_row("SPY（S&P500）", env.get("spy"), env.get("spy_ok"))
    vix_color = env.get("vix_color", "#999")
    vix_label = env.get("vix_label") or "取得失敗"
    env_section = f"""
<div class="section">
  <h2>📊 市場環境</h2>
  <table class="pos">
    <tr><th>指標</th><th style="text-align:right">値</th><th>判定</th></tr>
    {topix_row}
    {spy_row}
    <tr><td>VIX</td>
        <td colspan=2 style="color:{vix_color};font-weight:bold">{vix_label}</td></tr>
  </table>
</div>"""

    # --- アラートセクション ---
    critical = [a for a in all_alerts if a.level == "CRITICAL"]
    warn     = [a for a in all_alerts if a.level == "WARN"]
    info     = [a for a in all_alerts if a.level == "INFO"]

    def _section(title: str, items: list[Alert], no_msg: str) -> str:
        if items:
            return f'<div class="section"><h2>{title}</h2>' + \
                   "".join(_alert_card_html(a) for a in items) + "</div>"
        return f'<div class="section"><h2>{title}</h2><p class="no-alert">{no_msg}</p></div>'

    crit_sec = _section(
        "🚨 損切り・即時アクション必要",
        critical,
        "現時点で損切り条件に該当する銘柄はありません"
    )
    warn_sec = _section(
        "⚠️ 利確・縮小を検討",
        warn,
        "現時点で利確・縮小条件に該当する銘柄はありません"
    )
    info_sec = _section(
        "ℹ️ 情報・推奨アクション",
        info,
        "現時点で情報アラートはありません"
    )

    # --- ポジション一覧セクション ---
    rows = ""
    for p in positions:
        if p.get("code", "").startswith("_"):
            continue
        code   = p.get("code", "")
        name   = p.get("name", "")
        layer  = "波乗り(短)" if p.get("layer") == "short" else "長期保有"
        is_us  = _is_us(code)
        shares = p.get("shares", 0)
        cost   = p.get("entry_price") or p.get("avg_cost") or 0
        rows += (f"<tr><td>{code}</td><td>{name}</td><td>{layer}</td>"
                 f"<td>{shares:,}</td>"
                 f"<td>{_fmt_price(cost, is_us)}</td></tr>")

    pos_section = f"""
<div class="section">
  <h2>📋 監視中ポジション（{sum(1 for p in positions if not p.get('code','').startswith('_'))} 銘柄）</h2>
  <table class="pos">
    <tr><th>コード</th><th>銘柄名</th><th>層</th><th>数量</th><th>取得価格</th></tr>
    {rows}
  </table>
  <p style="font-size:11px;color:#999;margin-top:8px">
    ※ positions.json を編集してポジションを追加・変更できます。be_triggered=true に変更すると
    ブレークイーン発動済みとして扱われます。
  </p>
</div>"""

    total_alerts = len(all_alerts)
    subj_badge = f"🚨 要注意{len(critical)}件" if critical else (f"⚠️ 警戒{len(warn)}件" if warn else "異常なし")

    html = f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>{_CSS}</style></head><body>
<div class="wrap">
  <div class="header">
    <h1>波乗りトレード v3.2 — 売却アラート</h1>
    <p>{today} ／ 本日のアラート：{total_alerts} 件（CRITICAL:{len(critical)} / WARN:{len(warn)} / INFO:{len(info)}）</p>
  </div>
  {env_section}
  {crit_sec}
  {warn_sec}
  {info_sec}
  {pos_section}
  <div class="footer">
    波乗りトレード定義書 v3.2 ／ 自動生成レポート<br>
    positions.json を編集してポジション情報を更新してください。
  </div>
</div>
</body></html>"""
    return html, subj_badge


# ═══════════════════════════════════════════════════════
# メール送信
# ═══════════════════════════════════════════════════════
def send_email(html: str, subject: str) -> None:
    api_key    = os.environ.get("RESEND_API_KEY", "")
    to_addr    = os.environ.get("NOTIFY_EMAIL", "")
    from_addr  = os.environ.get("FROM_EMAIL", "nami-scanner@resend.dev")
    if not api_key or not to_addr:
        print("  [SKIP] RESEND_API_KEY または NOTIFY_EMAIL が未設定")
        return
    res = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": from_addr, "to": [to_addr], "subject": subject, "html": html},
        timeout=30,
    )
    if res.status_code == 200:
        print(f"  メール送信成功 → {to_addr}")
    else:
        print(f"  メール送信失敗: {res.status_code} {res.text}")


# ═══════════════════════════════════════════════════════
# メイン
# ═══════════════════════════════════════════════════════
def main() -> None:
    _load_dotenv()

    # positions.json 読み込み
    pos_path = Path(__file__).resolve().parent / "positions.json"
    if not pos_path.exists():
        print("  [ERROR] positions.json が見つかりません")
        return
    all_positions: list[dict] = json.loads(pos_path.read_text(encoding="utf-8"))
    positions = [p for p in all_positions if not p.get("code", "").startswith("_")]
    print(f"  ポジション読み込み: {len(positions)} 銘柄")

    # 市場環境チェック
    print("  市場環境チェック中...")
    env = check_market_env()
    print(f"    TOPIX: {env['topix']} / SPY: {env['spy']} / VIX: {env['vix_label']}")

    # 各銘柄チェック
    all_alerts: list[Alert] = []
    for pos in positions:
        code  = pos["code"]
        layer = pos.get("layer", "short")
        print(f"  [{code}] データ取得中...", end=" ")
        try:
            ticker = yf.Ticker(code)
            df_raw = ticker.history(period=PERIOD_D)
            if df_raw.empty:
                print("SKIP（データなし）")
                continue
            df = _calc_indicators(df_raw)
            print(f"rows={len(df)}", end=" ")

            if layer == "short":
                alerts = check_short(pos, df)
            else:
                df_w   = _calc_weekly(code)
                alerts = check_long(pos, df, df_w)

            print(f"→ {len(alerts)} alerts")
            all_alerts.extend(alerts)
        except Exception as e:
            print(f"ERROR: {e}")

    # HTML生成・送信
    html, badge = build_html(positions, all_alerts, env)
    today = datetime.date.today().strftime("%Y/%m/%d")
    subject = f"【波乗りアラート】{today} {badge}"
    print(f"\n  Subject: {subject}")
    send_email(html, subject)

    # ローカル確認用 HTML 出力
    out_path = Path(__file__).resolve().parent / "results" / "exit_alert_preview.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  プレビュー: {out_path}")


if __name__ == "__main__":
    main()
