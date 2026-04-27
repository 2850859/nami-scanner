# 波乗りスキャナー — セットアップ手順

## ファイル構成

```
nami-scanner/
  ├── .github/
  │   └── workflows/
  │       └── scan.yml        ← 毎日自動実行の設定
  ├── results/                ← スキャン結果（自動生成）
  │   ├── jpx400.json
  │   └── sp500.json
  ├── scan_jpx400.py          ← JPX400スキャンスクリプト
  ├── scan_sp500.py           ← S&P500スキャンスクリプト
  ├── index.html              ← JPX400ビューワー
  └── sp500.html              ← S&P500ビューワー
```

---

## STEP 1 — GitHubリポジトリ作成

1. https://github.com/new を開く
2. Repository name: `nami-scanner`
3. **Public** を選択
4. 「Create repository」をクリック

---

## STEP 2 — 全ファイルをアップロード

リポジトリのページで「Add file」→「Upload files」

以下をすべてアップロード：
- `.github/workflows/scan.yml`（フォルダごと）
- `scan_jpx400.py`
- `scan_sp500.py`
- `index.html`
- `sp500.html`

---

## STEP 3 — GitHub Pages を有効化

1. リポジトリの「Settings」タブ
2. 左メニュー「Pages」
3. Branch: **main** / フォルダ: **/ (root)** を選択
4. 「Save」をクリック

---

## STEP 4 — 初回スキャンを手動実行

1. リポジトリの「Actions」タブ
2. 左メニュー「毎日ゴールデンクロス スキャン」
3. 「Run workflow」→「Run workflow」をクリック
4. 約10〜20分待つ

---

## STEP 5 — スマホで確認

```
https://あなたのユーザー名.github.io/nami-scanner/
https://あなたのユーザー名.github.io/nami-scanner/sp500.html
```

---

## 自動実行スケジュール

| 時刻 | 内容 |
|------|------|
| 平日 16:15（JST） | JPX400スキャン（東証終値確定後） |
| 平日 07:00（JST翌朝） | S&P500スキャン（NY市場終値確定後） |

---

## スキャン結果の見方

| 表示 | 内容 |
|------|------|
| `GC 本日` | 本日 MA5 が MA10 を上抜け |
| `RANK S` | スコア75以上 — クロスまで1〜2日の可能性 |
| `RANK A` | スコア50〜74 — クロスまで3〜5日の可能性 |
| `RANK B` | スコア30〜49 — クロスまで6〜10日の可能性 |
| `MA5上` | MA5 > MA10 継続中 |
| `収束中` | 乖離が縮まっている |
| `加速` | 収束が加速している |
