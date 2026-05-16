# Surge にデプロイして URL を提出する手順

提出フォームに **公開 URL** を貼る形式向けです。

## 事前準備

1. **Node.js** が入っていること（`node -v` で確認）。
2. プロジェクトの **`docs/surge_site`** に `index.html` があること（図解つき提出ページ）。

## デプロイ（Surge）

PowerShell で：

```powershell
cd C:\Users\fujii-minipc\src\nami-scanner\docs\surge_site
npx surge .
```

初回は Surge が **メール認証** を求めます。表示される指示に従ってログインしてください。

### ドメイン名を指定する場合（任意）

```powershell
npx surge . nami-wave-xyz.surge.sh
```

`nami-wave-xyz` は **あなただけの英数字** に変える（既に取られていると別名を試す）。

指定しない場合も Surge がランダムな `xxxx.surge.sh` を案内します。

## URL を確認する

1. デプロイ完了後、ターミナルに **https://〜.surge.sh** が表示されます。
2. **ブラウザでその URL を開き**、図解ページが表示されるか確認します。
3. **スマホでも開けるか**（任意）確認すると安心です。

## 提出フォームへ

1. ポータルの **提出フォーム** を開く。
2. **URL 欄**に `https://あなたの名前.surge.sh` を貼り付ける。
3. **送信**する。

## 更新したとき

同じフォルダから再度：

```powershell
cd C:\Users\fujii-minipc\src\nami-scanner\docs\surge_site
npx surge .
```

同じドメインを指定すれば上書きデプロイできます。

## Surge 以外の例

- **GitHub Pages**：リポジトリの Settings → Pages で `docs/surge_site` などを公開する。
- **Netlify Drop**：`surge_site` フォルダをドラッグ＆ドロップで公開。

いずれも「静的ファイル（HTML）をホストして URL を得る」という点は同じです。
