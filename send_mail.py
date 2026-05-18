"""
スキャン結果をCSV添付メールで送信
- GC本日 + Sランク + Aランクの銘柄をCSVに出力
- Resend経由でメール送信
- YouTubeチャンネル最新情報セクションを追記（YOUTUBE_API_KEY 設定時）
"""
import os
import json
import csv
import io
import base64
import datetime
from pathlib import Path
import requests

try:
    from fetch_youtube_summary import build_youtube_html_section
    _YOUTUBE_AVAILABLE = True
except ImportError:
    _YOUTUBE_AVAILABLE = False


def _load_dotenv() -> None:
    """リポジトリ直下の .env を読み込む（未設定のキーのみ上書きしない）。"""
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


def fetch_vix() -> tuple[float | None, str, str]:
    """
    ^VIX の最新終値を yfinance で取得し、(値, ラベル, カラー) を返す。
    取得失敗時は (None, "取得失敗", "#999") を返す。
    """
    try:
        import yfinance as yf
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="2d")
        if hist.empty:
            return None, "取得失敗", "#999"
        val = float(hist["Close"].iloc[-1])
        if val >= 35:
            label, color = f"{val:.1f} 🔴 危険域（新規停止＋利確検討）", "#d93025"
        elif val >= 28:
            label, color = f"{val:.1f} 🟡 警戒域（新規エントリー停止）", "#f5a623"
        else:
            label, color = f"{val:.1f} 🟢 通常域", "#00955a"
        return val, label, color
    except Exception as e:
        print(f"  WARN: VIX 取得失敗: {e}")
        return None, "取得失敗", "#999"


def load_results(market: str) -> dict:
    """results/jpx400.json または sp500.json を読み込む"""
    path = f"results/{market}.json"
    if not os.path.exists(path):
        print(f"  WARN: {path} が見つかりません")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_signals(results: list) -> list:
    """GC本日 + Sランク + Aランクのみ抽出"""
    return [
        r for r in results
        if r.get("gc_today") or r.get("rank") in ("S", "A")
    ]


def make_csv(signals: list, market_label: str) -> str:
    """シグナル一覧を CSV 文字列に変換"""
    output = io.StringIO()
    writer = csv.writer(output)

    # ヘッダー
    writer.writerow([
        "市場", "ランク", "コード", "銘柄名", "終値",
        "MA5", "MA10", "乖離率(%)", "スコア",
        "GC本日", "MA5上昇", "収束中", "加速",
        "推定クロス日数", "MA5傾き", "MA10傾き",
    ])

    # データ
    for r in signals:
        writer.writerow([
            market_label,
            r.get("rank", ""),
            r.get("code", ""),
            r.get("name", ""),
            r.get("close", ""),
            r.get("ma5", ""),
            r.get("ma10", ""),
            r.get("diff_pct", ""),
            r.get("score", ""),
            "○" if r.get("gc_today") else "",
            "○" if r.get("ma5_above") else "",
            "○" if r.get("is_conv") else "",
            "○" if r.get("is_accel") else "",
            r.get("est_days", "") or "",
            r.get("ma5_slope", ""),
            r.get("ma10_slope", ""),
        ])

    return output.getvalue()


def make_tradingview_watchlist(jpx_signals: list, sp_signals: list, label: str = "") -> str:
    """
    TradingView にインポートできるウォッチリスト形式のテキストを生成する。
    フォーマット: ###,リスト名 の後に EXCHANGE:SYMBOL を1行ずつ
    JP株: 7203.T → TSE:7203
    US株: NVDA   → NASDAQ:NVDA（取引所不明のためTradingViewに任せる形式）
    """
    lines = [f"###,{label}" if label else "###,波乗りスキャナー S/A ランク"]

    if jpx_signals:
        lines.append("###,JPX400")
        for r in jpx_signals:
            code = str(r.get("code", ""))
            # "7203.T" → "TSE:7203"
            if code.upper().endswith(".T"):
                tv_sym = "TSE:" + code[:-2]
            else:
                tv_sym = "TSE:" + code
            lines.append(tv_sym)

    if sp_signals:
        lines.append("###,SP500")
        for r in sp_signals:
            code = str(r.get("code", ""))
            lines.append(code)  # TradingView は米国株をシンボルのみで解決可能

    return "\n".join(lines) + "\n"


def send_email(api_key: str, to_email: str, subject: str, html_body: str, attachments: list):
    """Resend API でメール送信（requestsライブラリ使用）"""
    url = "https://api.resend.com/emails"

    # 日本語対応のため json= 引数で渡す（requestsが自動でUTF-8エンコード）
    payload = {
        "from": "Nami Scanner <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "attachments": attachments,
    }

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
    }

    try:
        # json= でrequestsが自動でUTF-8 JSONを生成
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code in (200, 201):
            data = response.json()
            print(f"  OK メール送信成功: id={data.get('id', '')}")
            return True
        else:
            print(f"  NG メール送信失敗 (status={response.status_code})")
            print(f"  レスポンス: {response.text[:500]}")
            return False
    except Exception as e:
        print(f"  NG メール送信エラー: {e}")
        return False


def notify_backtest_email(
    *,
    summary_json_path: str,
    out_dir: str,
    prefix: str,
    metrics: dict,
    tickers: list,
    period: str,
    entry_mode: str,
) -> bool:
    """
    バックテスト完了を Resend で通知する。
    環境変数: RESEND_API_KEY, NOTIFY_EMAIL（既存のスキャン配信と同じ）
    """
    _load_dotenv()
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_email = os.environ.get("NOTIFY_EMAIL", "").strip()
    if not api_key or not to_email:
        print(
            "  [WARN] メール通知スキップ: RESEND_API_KEY または NOTIFY_EMAIL が未設定",
        )
        return False

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    tickers_s = " ".join(tickers) if tickers else "(なし)"
    subject = (
        f"[バックテスト完了] {prefix} ({entry_mode}) "
        f"{now.strftime('%Y-%m-%d %H:%M')} JST"
    )

    def _fmt_num(v, digits: int = 4) -> str:
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            if isinstance(v, float):
                return f"{v:.{digits}f}"
            return str(v)
        return str(v)

    rows_html = []
    labels = [
        ("total_return_pct", "総リターン (%)"),
        ("annual_return_pct", "年率リターン (%)"),
        ("max_drawdown_pct", "最大DD (%)"),
        ("sharpe_ratio", "シャープレシオ"),
        ("trade_count", "トレード数"),
        ("win_rate_pct", "勝率 (%)"),
        ("profit_factor", "プロフィットファクター"),
        ("final_capital", "最終資産"),
        ("avg_holding_days", "平均保有日数"),
    ]
    for key, label in labels:
        if key in metrics:
            rows_html.append(
                f"<tr><td style='padding:8px;border:1px solid #e0e6ed;'>{label}</td>"
                f"<td style='padding:8px;border:1px solid #e0e6ed;'>{_fmt_num(metrics.get(key))}</td></tr>",
            )

    err = metrics.get("error")
    err_block = (
        f"<p style='color:#d93025;'><strong>注意:</strong> {err}</p>" if err else ""
    )

    html_body = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, sans-serif; max-width: 640px; margin: 0 auto; padding: 20px; color: #333;">
  <h1 style="font-size: 18px;">バックテストが完了しました</h1>
  <p style="color:#666;font-size:14px;">
    期間: <code>{period}</code> · entry_mode: <code>{entry_mode}</code><br>
    銘柄: <code>{tickers_s}</code>
  </p>
  {err_block}
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <thead><tr style="background:#f5f7fa;">
      <th style="padding:8px;text-align:left;border:1px solid #e0e6ed;">指標</th>
      <th style="padding:8px;text-align:left;border:1px solid #e0e6ed;">値</th>
    </tr></thead>
    <tbody>{''.join(rows_html)}</tbody>
  </table>
  <p style="color:#666;font-size:13px;">添付: メトリクス・トレード明細・サマリーJSON（存在するもののみ）</p>
</body></html>"""

    attachments = []
    od = Path(out_dir)
    for rel_name in (
        f"{prefix}_metrics.csv",
        f"{prefix}_trades.csv",
        f"{prefix}_monthly.csv",
        f"{prefix}_by_symbol.csv",
        f"{prefix}_by_regime.csv",
    ):
        p = od / rel_name
        if p.is_file():
            with open(p, "rb") as f:
                raw = f.read()
            attachments.append(
                {
                    "filename": rel_name,
                    "content": base64.b64encode(raw).decode("utf-8"),
                },
            )

    sj = Path(summary_json_path)
    if sj.is_file():
        with open(sj, "rb") as f:
            raw = f.read()
        attachments.append(
            {
                "filename": sj.name,
                "content": base64.b64encode(raw).decode("utf-8"),
            },
        )

    print(f"\n  メール通知: {to_email} （添付 {len(attachments)} 件）")
    return send_email(api_key, to_email, subject, html_body, attachments)


def main(test: bool = False):
    _load_dotenv()
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_email = os.environ.get("NOTIFY_EMAIL", "").strip()

    if not api_key:
        print("NG RESEND_API_KEY が設定されていません")
        return
    if not to_email:
        print("NG NOTIFY_EMAIL が設定されていません")
        return

    if test:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        subject = f"[テスト] 波乗りスキャナー配信確認 ({now.strftime('%Y-%m-%d %H:%M')} JST)"
        html_body = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; padding: 20px;">
  <p>これは <strong>テスト配信</strong> です。</p>
  <p>RESEND_API_KEY と NOTIFY_EMAIL の組み合わせが正しく動いています。</p>
  <p style="color:#666;font-size:13px;">本番はシグナルがある日のみ送信されます（<code>python send_mail.py</code>）。</p>
</body></html>"""
        print(f"\n{'='*50}\nテストメール送信\n{'='*50}\n  宛先: {to_email}\n  件名: {subject}")
        send_email(api_key, to_email, subject, html_body, [])
        return

    # JST 現在日時
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    today_str = now.strftime("%Y-%m-%d")
    today_label = now.strftime("%m/%d")

    # ========================================
    # JPX400 / SP500 のシグナルを抽出
    # ========================================
    jpx_data = load_results("jpx400")
    sp_data = load_results("sp500")

    jpx_signals_1d = []
    sp_signals_1d = []

    if jpx_data:
        jpx_signals_1d = filter_signals(jpx_data.get("timeframes", {}).get("1d", []))
    if sp_data:
        sp_signals_1d = filter_signals(sp_data.get("timeframes", {}).get("1d", []))

    # 件数集計
    jpx_gc = len([r for r in jpx_signals_1d if r.get("gc_today")])
    jpx_s  = len([r for r in jpx_signals_1d if r.get("rank") == "S"])
    jpx_a  = len([r for r in jpx_signals_1d if r.get("rank") == "A"])

    sp_gc = len([r for r in sp_signals_1d if r.get("gc_today")])
    sp_s  = len([r for r in sp_signals_1d if r.get("rank") == "S"])
    sp_a  = len([r for r in sp_signals_1d if r.get("rank") == "A"])

    total_signals = jpx_gc + jpx_s + jpx_a + sp_gc + sp_s + sp_a

    if total_signals == 0:
        print("INFO: 本日のシグナルなし。メール送信をスキップします。")
        return

    # ========================================
    # VIX 取得
    # ========================================
    print("\n[VIX] 最新値を取得中...")
    vix_val, vix_label, vix_color = fetch_vix()
    print(f"  VIX: {vix_label}")

    # ========================================
    # GC追跡 勝率統計の読み込み
    # ========================================
    gc_stats = {}
    gc_total = 0
    gc_stats_path = "data/gc_stats.json"
    if os.path.exists(gc_stats_path):
        with open(gc_stats_path, "r", encoding="utf-8") as f:
            _s = json.load(f)
            gc_stats = _s.get("stats", {})
            gc_total = _s.get("total", 0)

    # ========================================
    # CSV 添付ファイルを作成
    # ========================================
    attachments = []

    if jpx_signals_1d:
        csv_text = make_csv(jpx_signals_1d, "JPX400")
        csv_bytes = ("\ufeff" + csv_text).encode("utf-8")
        attachments.append({
            "filename": f"jpx400_signals_{today_str}.csv",
            "content": base64.b64encode(csv_bytes).decode("utf-8"),
        })

    if sp_signals_1d:
        csv_text = make_csv(sp_signals_1d, "SP500")
        csv_bytes = ("\ufeff" + csv_text).encode("utf-8")
        attachments.append({
            "filename": f"sp500_signals_{today_str}.csv",
            "content": base64.b64encode(csv_bytes).decode("utf-8"),
        })

    # ========================================
    # TradingView ウォッチリスト添付（S/Aランクのみ）
    # ========================================
    tv_jpx = [r for r in jpx_signals_1d if r.get("gc_today") or r.get("rank") in ("S", "A")]
    tv_sp  = [r for r in sp_signals_1d  if r.get("gc_today") or r.get("rank") in ("S", "A")]
    if tv_jpx or tv_sp:
        tv_text = make_tradingview_watchlist(
            tv_jpx, tv_sp,
            label=f"波乗り S/A {today_str}",
        )
        attachments.append({
            "filename": f"tradingview_watchlist_{today_str}.txt",
            "content": base64.b64encode(tv_text.encode("utf-8")).decode("utf-8"),
        })
        print(f"  TradingView ウォッチリスト: JP {len(tv_jpx)}件 + US {len(tv_sp)}件")

    # ========================================
    # スクリーンショット添付（存在する場合）
    # ========================================
    screenshots = [
        ("results/screenshot_jpx400.png", f"jpx400_{today_str}.png"),
        ("results/screenshot_sp500.png",  f"sp500_{today_str}.png"),
    ]
    has_screenshot = False
    for src_path, attach_name in screenshots:
        if os.path.exists(src_path):
            with open(src_path, "rb") as f:
                img_bytes = f.read()
            attachments.append({
                "filename": attach_name,
                "content": base64.b64encode(img_bytes).decode("utf-8"),
            })
            has_screenshot = True
            print(f"  スクリーンショット添付: {attach_name}")

    # ========================================
    # GC追跡 勝率テーブル（f-string 内で複雑な join を書かない）
    # ========================================
    if gc_stats:
        _gc_rows = []
        for _p, _s in gc_stats.items():
            _wr_c = "#00955a" if _s["win_rate"] >= 50 else "#d93025"
            _pct_c = "#00955a" if _s["avg_pct"] >= 0 else "#d93025"
            _sign = "+" if _s["avg_pct"] >= 0 else ""
            _gc_rows.append(
                f'<tr><td style="padding:8px;border:1px solid #e0e6ed;">{_p}日後</td>'
                f'<td style="padding:8px;border:1px solid #e0e6ed;text-align:center;font-weight:bold;color:{_wr_c}">{_s["win_rate"]}%</td>'
                f'<td style="padding:8px;border:1px solid #e0e6ed;text-align:center;">{_s["wins"]}/{_s["total"]}件</td>'
                f'<td style="padding:8px;border:1px solid #e0e6ed;text-align:center;color:{_pct_c};font-weight:bold;">{_sign}{_s["avg_pct"]}%</td></tr>'
            )
        gc_stats_html = (
            '<table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px;">'
            '<thead><tr style="background:#f5f7fa;">'
            '<th style="padding:8px;border:1px solid #e0e6ed;text-align:left;">期間</th>'
            '<th style="padding:8px;border:1px solid #e0e6ed;text-align:center;">勝率</th>'
            '<th style="padding:8px;border:1px solid #e0e6ed;text-align:center;">件数</th>'
            '<th style="padding:8px;border:1px solid #e0e6ed;text-align:center;">平均騰落率</th>'
            '</tr></thead><tbody>'
            + "".join(_gc_rows)
            + "</tbody></table>"
        )
    else:
        gc_stats_html = (
            '<p style="color:#999;font-size:13px;">データ蓄積中...（GCシグナルが累積されると勝率が表示されます）</p>'
        )

    # ========================================
    # YouTube チャンネルサマリー取得
    # ========================================
    print("\n[YouTube] 最新動画を取得中...")
    youtube_section_html = ""
    if _YOUTUBE_AVAILABLE:
        try:
            youtube_section_html = build_youtube_html_section()
        except Exception as e:
            print(f"  WARN: YouTube セクション生成失敗（メール送信は続行）: {e}")
    else:
        print("  INFO: fetch_youtube_summary モジュールが見つかりません — スキップします")

    # ========================================
    # メール本文（HTML）作成
    # ========================================
    vix_tag = f" VIX:{vix_val:.0f}" if vix_val is not None else ""
    subject = f"[波乗りスキャナー] {today_label}{vix_tag} シグナル {total_signals}件 (GC:{jpx_gc + sp_gc} / S:{jpx_s + sp_s} / A:{jpx_a + sp_a})"

    html_body = f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">

  <div style="background: linear-gradient(135deg, #0099cc, #00d4ff); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
    <h1 style="margin: 0; font-size: 22px;">🌊 波乗りスキャナー</h1>
    <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 13px;">{today_str} スキャン結果</p>
  </div>

  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px;">市場環境</h2>
  <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
    <tbody>
      <tr>
        <td style="padding: 10px; border: 1px solid #e0e6ed; font-weight: bold; width: 80px;">VIX</td>
        <td style="padding: 10px; border: 1px solid #e0e6ed; font-weight: bold; color: {vix_color};">{vix_label}</td>
      </tr>
    </tbody>
  </table>

  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px;">本日のシグナル集計</h2>

  <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
    <thead>
      <tr style="background: #f5f7fa;">
        <th style="padding: 10px; text-align: left; border: 1px solid #e0e6ed;">市場</th>
        <th style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; color: #00b85a;">GC本日</th>
        <th style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; color: #f5a623;">RANK S</th>
        <th style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; color: #f5c842;">RANK A</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding: 10px; border: 1px solid #e0e6ed;">JPX400</td>
        <td style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; font-weight: bold;">{jpx_gc}件</td>
        <td style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; font-weight: bold;">{jpx_s}件</td>
        <td style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; font-weight: bold;">{jpx_a}件</td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #e0e6ed;">SP500</td>
        <td style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; font-weight: bold;">{sp_gc}件</td>
        <td style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; font-weight: bold;">{sp_s}件</td>
        <td style="padding: 10px; text-align: center; border: 1px solid #e0e6ed; font-weight: bold;">{sp_a}件</td>
      </tr>
    </tbody>
  </table>

  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px;">添付ファイル</h2>
  <p style="color: #666; font-size: 13px;">
    本日の<strong>GC本日・SランクとAランク</strong>の銘柄一覧をCSVで添付しました。<br>
    Excelで開く場合は文字化けせずに表示されます。
  </p>
  <p style="color: #666; font-size: 13px; margin-top: 8px;">
    <strong>tradingview_watchlist_{today_str}.txt</strong> を TradingView の
    「ウォッチリスト → インポート」で読み込むと銘柄が一括登録できます。
  </p>
  {'<p style="color: #666; font-size: 13px; margin-top: 8px;">各市場のスキャン結果画面のスクリーンショットも添付しています。</p>' if has_screenshot else ''}

  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px;">GC追跡 勝率実績（累計 {gc_total}件）</h2>
  {gc_stats_html}

  {youtube_section_html}

  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px;">ウェブ版で確認</h2>
  <p>
    <a href="https://2850859.github.io/nami-scanner/" style="display: inline-block; padding: 10px 20px; background: #00d4ff; color: white; text-decoration: none; border-radius: 5px; margin-right: 10px;">JPX400</a>
    <a href="https://2850859.github.io/nami-scanner/sp500.html" style="display: inline-block; padding: 10px 20px; background: #e84560; color: white; text-decoration: none; border-radius: 5px;">SP500</a>
  </p>

  <hr style="border: none; border-top: 1px solid #e0e6ed; margin: 30px 0 15px;">
  <p style="color: #999; font-size: 11px; text-align: center;">
    このメールは GitHub Actions から自動配信されています<br>
    波乗りスキャナー - MA5 × MA10 ゴールデンクロス検出ツール
  </p>

</body>
</html>"""

    # ========================================
    # 送信
    # ========================================
    print(f"\n{'='*50}")
    print(f"メール送信開始")
    print(f"{'='*50}")
    print(f"  宛先: {to_email}")
    print(f"  件名: {subject}")
    print(f"  添付: {len(attachments)} ファイル")
    print(f"  シグナル合計: {total_signals} 件")

    send_email(api_key, to_email, subject, html_body, attachments)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="スキャン結果メール送信（Resend）")
    parser.add_argument(
        "--test",
        action="store_true",
        help="シグナル有無に関係なくテストメールを1通だけ送信する",
    )
    args = parser.parse_args()
    main(test=args.test)
