# DOUJIN RANKIDLE

## API RANKING

RankIdleは現在、DMM Web Service APIの `site=FANZA` / `service=doujin` /
`floor=digital_doujin` / `sort=rank` をメインランキングとして1日4回定期観測します。
これはFANZA公式サイトの1時間・24時間ランキングとは別の指標です。既存の1H / 24Hデータと
手動取得機能は削除せず、**SPECIAL OBSERVATION**として保存・表示を継続します。

API取得結果は `data/fanza/api/current.json` と90日分のhistory、直近10 snapshotの
`data/analytics/fanza_api.json`、人間確認用の `data/posts/fanza_api_candidates.json` に保存します。
APIエラー時は処理を失敗させ、既存のcurrent、history、analytics、投稿候補を変更しません。

## FANZA 24H SALE WATCH

24時間ランキングの確定済み商品カード内だけから現在価格、通常価格、割引率、終了表示を取得します。1時間ランキングではセール解析を実行せず、`price: 0` を引き続き許容します。通常価格と現在価格がある場合に限り割引率を補完し、前回24Hとの差から SALE START / DISCOUNT UP / PRICE DROP / SALE END を記録します。

HOT SALE はセール中かつ「30%以上」「TOP10」「5ランク以上上昇」のいずれか、強いHOT SALEは30%以上かつTOP10です。SALE候補は自動投稿せず、イベントキー（商品・イベント種別・割引率・価格）で重複を防ぎ、優先度順に最大5件生成します。

FANZAモジュールの商品ランキングを1時間ごとに収集し、GitHub Pagesで表示する放置ゲーム風ダッシュボードです。FANZAは収集モジュールのひとつとして分離してあり、将来ほかのストアを追加できます。

## ゲームデータ

`status.json` は直近巡回の `items_collected` / `runs_today` に加え、`first_run`、`last_run`、`total_runs`、`total_items_collected`、`mode` を保持します。EXPは巡回成功ごとに5、取得商品ごとに1を加算し、100 EXPごとにレベルが上がります。実績は保存せず、累積巡回・商品数から画面表示時に判定します。

旧形式の `status.json` は自動移行されます。`first_run` がない場合は既存の `last_run`、`total_items_collected` がない場合は既存の `items_collected` を初期値として引き継ぎます。

## セットアップ

1. FANZA APIの実データを使う場合は、リポジトリの **Settings → Secrets and variables → Actions** に `DMM_API_ID` と `DMM_AFFILIATE_ID` を登録します。
2. **Settings → Pages** の公開元を `Deploy from a branch`、対象を既定ブランチの `/docs` にします。
3. Actionsの **Collect FANZA products** を手動実行します。以後はJST 03:17 / 09:17 / 14:17 / 22:17に自動実行されます。

APIの対象を変更する場合は、Workflowの環境変数に `FANZA_SERVICE`、`FANZA_FLOOR`、`FANZA_HITS`（最大100）を追加してください。FANZA同人向けの既定値はDMM Web Serviceのフロア体系に合わせた `doujin` / `digital_doujin` / `100` です。

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

### DMM APIランキング検証（dry run）

`python -m src.verify_dmm_api` はDMM APIのFANZA同人TOP20と保存済みの1H・24H TOP20を比較し、`data/verify/dmm_api_latest.json` だけに結果を書き込みます。本番ランキング、履歴、分析、レポート、投稿候補、EXP、`docs/data` は更新しません。認証情報、手動ランキング、またはAPI項目が不足する場合は本番処理へフォールバックせず失敗します。Actionsではscheduleを持たない **Verify DMM API ranking** を手動実行し、結果をartifactとして取得できます。

## v0.3 modes

The collector selects `live` only when both DMM credentials exist, otherwise selects
`public` when `PUBLIC_WATCH_ENABLED=true`, then uses a manual import when present, and otherwise falls back to `mock`. Public Watch reads
only the configured public ranking page, checks `robots.txt`, stores no images or review
text, and stops without evasion or destructive replacement on access errors. Set
`POST_COOLDOWN_HOURS` (default: 24) to tune candidate suppression. Candidates are for
human review only; this project does not post to X.

### Age gate and supported data sources

Public Watch does not inject cookies, accept the age check, or otherwise evade access
controls. If the final response URL contains `/age_check/`, it records
`public_watch_status: "age_gate"` and `last_public_watch_error: "FANZA age verification page reached"`.
The repository currently contains no official unauthenticated DMM/FANZA ranking API or
feed. The only structured official source implemented here is the authenticated DMM
Affiliate API (`src/providers/fanza_api.py`). Public HTML therefore remains monitoring
only and is not treated as a dependable input while the age gate is present.

Until DMM API credentials are available, save a manually obtained ranking as
`data/import/fanza.json`. It may be either an array or `{ "items": [...] }`; each item
needs `rank`, `title`, and either `id` or `url`, with optional `price` and `url`. The
collector validates this file and feeds it into the existing rank-difference, Trend
Score, history, and post-candidate pipeline. When Public Watch reaches the age gate it
keeps the explicit age-gate status while processing this import; without Public Watch,
the import is selected ahead of mock mode. Post candidates remain review/copy material
only—there is no automatic posting.

## v0.4 semi-auto import

Pages最下部の **IMPORT TOOLS** で **COPY BOOKMARKLET** を押し、作成したブラウザのブックマークのURL欄へ貼り付けます。ユーザー自身が通常のブラウザでFANZAランキングを表示してからブックマークを実行すると、表示済みの商品について順位・タイトル・価格・商品URL・cidだけを含むJSONがコピーされます。年齢確認の同意、Cookie、ログイン情報、レビュー、画像にはアクセスしません。Clipboard APIが使えない場合は手動コピー欄が開きます。

コピーしたJSONはPagesのValidator/Previewで確認後、`data/import/fanza.json`へ保存してCommitしてください。CommitするとActionsが自動実行され、表示が更新されます。v0.4の `{ "source": "fanza_manual", "captured_at": "...", "items": [...] }` と従来の `{ "items": [...] }` / 配列形式を受け付けます。同じ`captured_at`または同一内容を再実行しても巡回数、商品数、EXP、Trendイベントは加算しません。Pagesは読み取り専用で、GitHubへの保存、PATの保持、Xへの投稿は行いません。
# Weekly Trend Report

JSTの月曜日00:00〜日曜日23:59を一週として、`data/fanza/1h/history/` と
`data/fanza/24h/history/` の保存済みスナップショットから週次レポートを生成します。
結果は `data/reports/weekly/latest.json` と週開始日名の履歴ファイルに保存され、
GitHub Pages用の `docs/data/reports/weekly/` にも同期されます。7日分が揃わない週は
`data_status: "PARTIAL"` となります。数値は販売数や売上ではなくランキング内での観測です。
