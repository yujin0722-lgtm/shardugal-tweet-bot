# shardugal-tweet-bot

アニメ『天幕のシャードゥーガル』に関するツイートを毎日自動で検索し、Notionのデータベースに登録するボットです。GitHub Actions上で完全に自動実行され、パソコンを起動しておく必要はありません。

## 何をするか

毎日 UTC 03:00（日本時間12:00）に、X (Twitter) のAPIで以下のキーワードを検索します。

- `#天幕のシャードゥーガル`
- `天幕のシャードゥーガル`

見つかった新着ツイート（本文・URL・投稿者・投稿日時）を、Notionのデータベース「シャードゥーガル ツイート考証コレクション」に新規ページとして追加します。

カテゴリ・タグ・要約はAIによる自動判定を行っておらず、空欄で登録されます。内容を確認しながら手動で入力する運用です。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `fetch_and_push.py` | X APIへの問い合わせとNotionへの書き込みを行う本体プログラム |
| `.github/workflows/shardugal-tweets.yml` | 毎日12:00に`fetch_and_push.py`を実行するスケジュール設定 |
| `state.json` | 前回どこまで取得したかの記録。同じツイートを再取得して課金されるのを防ぐために使用 |
| `run_log.txt` | 実行結果のログ（正常終了時のみ更新） |

## 必要な設定（Repository Secrets）

`Settings → Secrets and variables → Actions` に以下の2つを登録しています。

- `X_BEARER_TOKEN` … X APIのBearer Token
- `NOTION_TOKEN` … Notion Internal Integrationのトークン

Notion側では、書き込み先データベースをこのIntegrationと共有（コネクト）しておく必要があります。

## 動作確認・停止方法

- 実行履歴の確認: [Actionsタブ](https://github.com/yujin0722-lgtm/shardugal-tweet-bot/actions)
- 手動実行: Actionsタブ →「シャードゥーガル ツイート収集」→「Run workflow」
- 一時停止: Actionsタブ →「シャードゥーガル ツイート収集」→「•••」→「Disable workflow」（いつでも再開可能）
- 完全に終了する場合: `Settings` の一番下から「Delete this repository」（元に戻せません）

## 収集データの確認先

Notionデータベース: https://app.notion.com/p/9deddf2696c54d1ebc3d50695e3e275d

## 補足

『天幕のシャードゥーガル』の放送は2026年9月末に終了予定のため、それに合わせて本ボットの停止を検討しています。
