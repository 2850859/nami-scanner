"""
YouTubeチャンネルの最新動画を取得し、Geminiで要約・波乗りルール矛盾フラグを付与する。

使い方:
  単体テスト: python fetch_youtube_summary.py
  send_mail.py から呼ぶ: build_youtube_html_section() を import して使う

必要な環境変数:
  YOUTUBE_API_KEY  : Google Cloud の YouTube Data API v3 キー
  GEMINI_API_KEY   : Gemini API キー（未設定の場合は説明文のみで要約スキップ）
"""

import json
import os
import re
import datetime
from typing import Optional

import google.generativeai as genai
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# ──────────────────────────────────────────
# 監視チャンネル定義
# is_base=True のチャンネルが波乗りシステム創始者（矛盾判定の基準ではなくラベル用）
# ──────────────────────────────────────────
CHANNELS = [
    {"name": "波乗りチャート向川", "handle": "chart-mukogawa", "is_base": True},
    {"name": "1up投資",            "handle": "1up794",          "is_base": False},
    {"name": "CLEARTRADE",         "handle": "CLEARTRADEMrK7",  "is_base": False},
    {"name": "トレードラボ",       "handle": "tradelabo2222",   "is_base": False},
    {"name": "お茶のゴールドマン", "handle": "o-chan_goldman",  "is_base": False},
]

LOOKBACK_HOURS = 24
TRANSCRIPT_MAX_CHARS = 8_000
SYSTEM_SPEC_MAX_CHARS = 3_000


# ──────────────────────────────────────────
# YouTube API ヘルパー
# ──────────────────────────────────────────

def _get_channel_id(youtube, handle: str) -> Optional[str]:
    """@ハンドルから channel_id を解決する。見つからなければ None。"""
    try:
        resp = youtube.channels().list(
            forHandle=f"@{handle}", part="id"
        ).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"  WARN: チャンネルID取得失敗 (@{handle}): {e}")
        return None


def _get_recent_videos(youtube, channel_id: str, hours: int = LOOKBACK_HOURS) -> list:
    """過去 hours 時間以内に公開された動画を最大5件取得する。"""
    published_after = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = youtube.search().list(
            channelId=channel_id,
            part="id,snippet",
            order="date",
            publishedAfter=published_after,
            type="video",
            maxResults=5,
        ).execute()
    except Exception as e:
        print(f"  WARN: 動画一覧取得失敗 (channel={channel_id}): {e}")
        return []

    return [
        {
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"],
            "description": item["snippet"].get("description", "")[:500],
        }
        for item in resp.get("items", [])
    ]


def _get_transcript(video_id: str) -> str:
    """字幕テキストを取得する（日本語優先、英語フォールバック）。取得不可なら空文字。"""
    try:
        segments = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["ja", "ja-JP", "en"]
        )
        return " ".join(s["text"] for s in segments)[:TRANSCRIPT_MAX_CHARS]
    except (TranscriptsDisabled, NoTranscriptFound):
        return ""
    except Exception as e:
        print(f"  WARN: 字幕取得失敗 (video={video_id}): {e}")
        return ""


# ──────────────────────────────────────────
# Gemini 要約
# ──────────────────────────────────────────

def _load_system_spec() -> str:
    """trade_rules/system_spec.md を読み込む。"""
    spec_path = os.path.join(os.path.dirname(__file__), "trade_rules", "system_spec.md")
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            return f.read()[:SYSTEM_SPEC_MAX_CHARS]
    except Exception:
        return ""


def _summarize(
    title: str,
    description: str,
    transcript: str,
    system_spec: str,
    channel_name: str,
) -> dict:
    """Gemini で要約 + 波乗りルール矛盾フラグを生成する。

    Returns:
        {"summary": str, "conflict": bool, "conflict_detail": str}
    """
    content = transcript or description
    if not content:
        return {"summary": "（内容を取得できませんでした）", "conflict": False, "conflict_detail": ""}

    prompt = f"""以下の YouTube 動画を分析してください。

チャンネル名: {channel_name}
タイトル: {title}
内容:
{content}

---
波乗りトレードシステムの主要ルール（参考）:
{system_spec}

---
以下の JSON 形式のみで回答してください（コードブロック不要）:
{{
  "summary": "3〜5行で要点をまとめた要約（投資家が重視すべき情報）",
  "conflict": true または false（波乗りルールと明確に相反する主張がある場合 true）,
  "conflict_detail": "矛盾がある場合の具体的な説明（なければ空文字）"
}}"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        return {
            "summary": f"（要約生成エラー: {e}）",
            "conflict": False,
            "conflict_detail": "",
        }


# ──────────────────────────────────────────
# HTML 生成（send_mail.py から呼ばれる公開 API）
# ──────────────────────────────────────────

def build_youtube_html_section() -> str:
    """毎朝のスキャンメールに追記する YouTube セクション HTML を返す。

    YOUTUBE_API_KEY が未設定の場合は空文字を返す（メールへの影響なし）。
    GEMINI_API_KEY が未設定の場合は要約なしでタイトルのみ表示する。
    """
    youtube_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not youtube_key:
        print("  INFO: YOUTUBE_API_KEY 未設定 — YouTube セクションをスキップします")
        return ""

    if gemini_key:
        genai.configure(api_key=gemini_key)

    youtube = build("youtube", "v3", developerKey=youtube_key)
    system_spec = _load_system_spec()

    rows_html: list[str] = []

    for ch in CHANNELS:
        label = ("⭐ " if ch["is_base"] else "") + ch["name"]
        print(f"  YouTube: {label} を取得中...")

        channel_id = _get_channel_id(youtube, ch["handle"])
        if not channel_id:
            rows_html.append(_row_html(label, "（チャンネルが見つかりません）", "", False, ""))
            continue

        videos = _get_recent_videos(youtube, channel_id)
        if not videos:
            rows_html.append(_row_html(label, "本日更新なし", "", False, ""))
            continue

        for v in videos:
            transcript = _get_transcript(v["video_id"]) if gemini_key else ""
            result = (
                _summarize(v["title"], v["description"], transcript, system_spec, ch["name"])
                if gemini_key
                else {"summary": v["description"] or "（Gemini未設定のため要約なし）", "conflict": False, "conflict_detail": ""}
            )
            video_url = f"https://www.youtube.com/watch?v={v['video_id']}"
            title_link = f'<a href="{video_url}" style="color:#0099cc;font-weight:bold;">{_esc(v["title"])}</a>'
            rows_html.append(
                _row_html(
                    label,
                    title_link,
                    result.get("summary", ""),
                    result.get("conflict", False),
                    result.get("conflict_detail", ""),
                )
            )

    if not rows_html:
        return ""

    return f"""
  <h2 style="font-size: 16px; border-bottom: 2px solid #00d4ff; padding-bottom: 8px; margin-top: 30px;">
    📺 YouTube チャンネル最新情報（過去24時間）
  </h2>
  <p style="color:#666;font-size:13px;">⭐ = 波乗りシステム創始者 &nbsp;|&nbsp; ⚠️ = 波乗りルールとの矛盾あり</p>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;font-size:13px;">
    <thead>
      <tr style="background:#f5f7fa;">
        <th style="padding:8px;border:1px solid #e0e6ed;text-align:left;white-space:nowrap;">チャンネル</th>
        <th style="padding:8px;border:1px solid #e0e6ed;text-align:left;">最新動画・要約</th>
        <th style="padding:8px;border:1px solid #e0e6ed;text-align:left;white-space:nowrap;">矛盾チェック</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
"""


# ──────────────────────────────────────────
# 内部ユーティリティ
# ──────────────────────────────────────────

def _esc(text: str) -> str:
    """HTML 特殊文字をエスケープする。"""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _row_html(
    channel_label: str,
    title_or_status: str,
    summary: str,
    conflict: bool,
    conflict_detail: str,
) -> str:
    summary_html = f'<br><span style="color:#444;font-size:12px;">{_esc(summary)}</span>' if summary else ""
    if conflict:
        conflict_html = (
            '<span style="color:#d93025;font-weight:bold;">⚠️ 矛盾</span>'
            + (f'<br><span style="font-size:11px;color:#d93025;">{_esc(conflict_detail)}</span>' if conflict_detail else "")
        )
    else:
        conflict_html = '<span style="color:#999;">—</span>'

    return (
        f'<tr>'
        f'<td style="padding:8px;border:1px solid #e0e6ed;vertical-align:top;white-space:nowrap;">{channel_label}</td>'
        f'<td style="padding:8px;border:1px solid #e0e6ed;vertical-align:top;">{title_or_status}{summary_html}</td>'
        f'<td style="padding:8px;border:1px solid #e0e6ed;vertical-align:top;">{conflict_html}</td>'
        f'</tr>'
    )


# ──────────────────────────────────────────
# 単体テスト用エントリポイント
# ──────────────────────────────────────────

if __name__ == "__main__":
    html = build_youtube_html_section()
    if html:
        out = "youtube_section_preview.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"<!DOCTYPE html><html lang='ja'><head><meta charset='UTF-8'></head><body>{html}</body></html>")
        print(f"\n  プレビューHTML を書き出しました: {out}")
    else:
        print("\n  YOUTUBE_API_KEY を設定してから実行してください")
