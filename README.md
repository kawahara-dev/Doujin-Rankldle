# DOUJIN RANKIDLE

FANZAモジュールの商品ランキングを1時間ごとに収集し、GitHub Pagesで表示する放置ゲーム風ダッシュボードです。FANZAは収集モジュールのひとつとして分離してあり、将来ほかのストアを追加できます。

## ゲームデータ

`status.json` は直近巡回の `items_collected` / `runs_today` に加え、`first_run`、`last_run`、`total_runs`、`total_items_collected`、`mode` を保持します。EXPは巡回成功ごとに5、取得商品ごとに1を加算し、100 EXPごとにレベルが上がります。実績は保存せず、累積巡回・商品数から画面表示時に判定します。

旧形式の `status.json` は自動移行されます。`first_run` がない場合は既存の `last_run`、`total_items_collected` がない場合は既存の `items_collected` を初期値として引き継ぎます。

## セットアップ

1. FANZA APIの実データを使う場合は、リポジトリの **Settings → Secrets and variables → Actions** に `DMM_API_ID` と `DMM_AFFILIATE_ID` を登録します。
2. **Settings → Pages** の公開元を `Deploy from a branch`、対象を既定ブランチの `/docs` にします。
3. Actionsの **Collect FANZA products** を手動実行します。以後は毎時17分に自動実行されます。

APIの対象を変更する場合は、Workflowの環境変数に `FANZA_SERVICE`、`FANZA_FLOOR`、`FANZA_HITS`（最大100）を追加してください。既定値は `digital` / `videoa` / `100` です。

2つのAPI認証情報がともに設定されている場合だけFANZA APIを使用します。どちらかが未設定の場合は処理を失敗させず、開発用モックランキングを生成します。`status.json` とPagesのバッジで `mock` / `DEMO MODE` または `live` / `LIVE MODE` を確認できます。

## ローカル実行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DMM_API_ID="..."
export DMM_AFFILIATE_ID="..."
python src/collector.py
cp data/*.json docs/data/
python -m http.server 8000 -d docs
```

ブラウザで <http://localhost:8000> を開いて確認できます。API認証情報がない場合はモックモードで実行します。認証情報があるときのAPIエラーは処理を失敗させ、既存JSONを上書きしません。

## v0.3 modes

The collector selects `live` only when both DMM credentials exist, otherwise selects
`public` when `PUBLIC_WATCH_ENABLED=true`, and falls back to `mock`. Public Watch reads
only the configured public ranking page, checks `robots.txt`, stores no images or review
text, and stops without evasion or destructive replacement on access errors. Set
`POST_COOLDOWN_HOURS` (default: 24) to tune candidate suppression. Candidates are for
human review only; this project does not post to X.
