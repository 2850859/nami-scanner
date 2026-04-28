"""
Playwrightを使ってindex.html / sp500.html のスクリーンショットを撮影し
results/ に保存する。

ローカルHTTPサーバー（port 8765）を一時起動して、JavaScriptによる
results/*.json の読み込みが正常に動作するようにする。
"""
import os
import sys
import time
import subprocess

from playwright.sync_api import sync_playwright

PORT = 8765
OUTPUT_DIR = "results"

PAGES = [
    (f"http://localhost:{PORT}/index.html",  "screenshot_jpx400.png"),
    (f"http://localhost:{PORT}/sp500.html",   "screenshot_sp500.png"),
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # プロジェクトルートからローカルHTTPサーバーを起動
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # サーバー起動待機

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            for url, filename in PAGES:
                page = browser.new_page(viewport={"width": 480, "height": 1080})
                try:
                    # networkidle でデータ fetch 完了を待つ
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                    # JS レンダリング追加待機
                    page.wait_for_timeout(2_000)

                    out_path = os.path.join(OUTPUT_DIR, filename)
                    page.screenshot(path=out_path, full_page=False)
                    print(f"  OK スクリーンショット保存: {out_path}")
                except Exception as e:
                    print(f"  WARN: {url} のスクリーンショット失敗: {e}")
                finally:
                    page.close()

            browser.close()
    finally:
        server.terminate()
        server.wait()
        print("  ローカルHTTPサーバーを停止しました")


if __name__ == "__main__":
    main()
