"""
スキャン結果をCSV添付メールで送信
- GC本日 + Sランク + Aランクの銘柄をCSVに出力
- Resend経由でメール送信
"""
import os
import json
import csv
import io
import base64
import datetime
import requests


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


def main():
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_email = os.environ.get("NOTIFY_EMAIL", "").strip()

    if not api_key:
        print("NG RESEND_API_KEY が設定されていません")
        return
    if not to_email:
        print("NG NOTIFY_EMAIL が設定されていません")
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
    # メール本文（HTML）作成
    # ========================================
    subject = f"[波乗りスキャナー] {today_label} シグナル {total_signals}件 (GC:{jpx_gc + sp_gc} / S:{jpx_s + sp_s} / A:{jpx_a + sp_a})"

    html_body = f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">

  <div style="background: linear-gradient(135deg, #0099cc, #00d4ff); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
    <h1 style="margin: 0; font-size: 22px;">🌊 波乗りスキャナー</h1>
    <p style="margin: 8px 0 0 0; opacity: 0.9; font-size: 13px;">{today_str} スキャン結果</p>
  </div>

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
    本日のGC本日・Sランク・Aランクの銘柄一覧をCSVで添付しました。<br>
    Excelで開く場合は文字化けせずに表示されます。
  </p>
  {'<p style="color: #666; font-size: 13px; margin-top: 8px;">各市場のスキャン結果画面のスクリーンショットも添付しています。</p>' if has_screenshot else ''}

  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px;">GC追跡 勝率実績（累計 {gc_total}件）</h2>
  {gc_stats_html}

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
    main()
