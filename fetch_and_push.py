#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_and_push.py

『天幕のシャードゥーガル』関連のツイートを X (Twitter) の公式APIで検索し、
そのままNotionのデータベースに新規ページとして書き込む、GitHub Actions専用スクリプトです。

ローカルPC版(fetch_tweets.py)と違い、このスクリプトはX APIへの問い合わせと
Notionへの書き込みの両方を1回で行います(AIによる自動タグ付けは行いません。
カテゴリ・タグ・要約はNotion側で手動で入力する想定です)。

必要な環境変数(GitHub Actionsのリポジトリ Secretsとして設定):
  X_BEARER_TOKEN … XのBearer Token
  NOTION_TOKEN    … Notion Internal Integrationのトークン

状態管理:
  state.json に「最後に取得したツイートID」を保存し、次回はそれより新しい
  ツイートだけを取得します(同じツイートへの再課金を防ぐため)。
  このファイルはワークフロー側でリポジトリにコミットし直すことで、
  実行のたびに最新の状態を引き継ぎます。
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ---- 設定 ----------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_FILE = os.path.join(BASE_DIR, "run_log.txt")

KEYWORDS = ["#天幕のシャードゥーガル", "天幕のシャードゥーガル"]
SEARCH_QUERY = "(" + " OR ".join(KEYWORDS) + ") -is:retweet"
SEARCH_URL = "https://api.x.com/2/tweets/search/recent"

NOTION_DATABASE_ID = "9deddf2696c54d1ebc3d50695e3e275d"
NOTION_PAGES_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


# ---- ユーティリティ --------------------------------------------------------

def log(msg: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"last_id": None}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        log("警告: state.json の読み込みに失敗しました。初回実行として扱います。")
        return {"last_id": None}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


# ---- X API ----------------------------------------------------------------

def call_x_api(token: str, since_id: str = None) -> dict:
    params = {
        "query": SEARCH_QUERY,
        "max_results": "100",
        "tweet.fields": "created_at,author_id,text,lang,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,name",
    }
    if since_id:
        params["since_id"] = since_id
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        log(f"エラー: X APIがエラーを返しました (HTTP {e.code})")
        log(f"詳細: {error_body}")
        if e.code == 401:
            log("→ Bearer Tokenが無効か期限切れの可能性があります。")
        elif e.code == 429:
            log("→ レート制限、またはクレジット残高不足の可能性があります。console.x.comで確認してください。")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"エラー: X APIへの接続に失敗しました: {e}")
        sys.exit(1)


# ---- Notion API -------------------------------------------------------------

def create_notion_page(notion_token: str, tweet: dict, username: str, name: str) -> bool:
    title = truncate(tweet.get("text", "(本文なし)"), 60)
    body_text = truncate(tweet.get("text", ""), 2000)
    author_display = truncate(f"{name} (@{username})" if name else f"@{username}", 2000)
    url = f"https://x.com/{username}/status/{tweet['id']}"

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "タイトル": {"title": [{"text": {"content": title}}]},
            "URL": {"url": url},
            "投稿者": {"rich_text": [{"text": {"content": author_display}}]},
            "投稿日時": {"date": {"start": tweet.get("created_at")}},
            "本文": {"rich_text": [{"text": {"content": body_text}}]},
            "Tweet ID": {"rich_text": [{"text": {"content": tweet["id"]}}]},
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(NOTION_PAGES_URL, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {notion_token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        log(f"エラー: Notionへの書き込みに失敗しました (tweet {tweet['id']}, HTTP {e.code})")
        log(f"詳細: {error_body}")
        if e.code == 404:
            log("→ NotionのデータベースがこのIntegrationと共有されていない可能性があります。")
        elif e.code == 401:
            log("→ NOTION_TOKENが無効な可能性があります。")
        return False
    except urllib.error.URLError as e:
        log(f"エラー: Notionへの接続に失敗しました: {e}")
        return False


# ---- メイン処理 --------------------------------------------------------------

def main() -> None:
    log("=== 収集開始 ===")
    log(f"検索クエリ: {SEARCH_QUERY}")

    x_token = os.environ.get("X_BEARER_TOKEN")
    notion_token = os.environ.get("NOTION_TOKEN")
    if not x_token:
        log("エラー: 環境変数 X_BEARER_TOKEN が設定されていません。")
        sys.exit(1)
    if not notion_token:
        log("エラー: 環境変数 NOTION_TOKEN が設定されていません。")
        sys.exit(1)

    state = load_state()
    since_id = state.get("last_id")
    if since_id:
        log(f"since_id: {since_id} より新しいツイートのみ取得します")
    else:
        log("初回実行のため、直近7日分をまとめて取得します")

    data = call_x_api(x_token, since_id=since_id)

    tweets = data.get("data", [])
    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

    log(f"X APIから {len(tweets)} 件のツイートを取得しました")

    written = 0
    failed = 0
    max_id = int(since_id) if since_id else 0

    # 古い順に処理(idが小さい順)して、途中で失敗してもstateが変に飛ばないようにする
    tweets_sorted = sorted(tweets, key=lambda t: int(t["id"]))

    for tweet in tweets_sorted:
        tid = tweet["id"]
        author = users.get(tweet.get("author_id"), {})
        username = author.get("username", "unknown")
        name = author.get("name", "")

        ok = create_notion_page(notion_token, tweet, username, name)
        if ok:
            written += 1
            max_id = max(max_id, int(tid))
        else:
            failed += 1
            # 失敗したツイートより先には進めない(次回また取得し直せるように)
            break

    state["last_id"] = str(max_id) if max_id else since_id
    save_state(state)

    log(f"Notionに書き込み成功: {written} 件 / 失敗: {failed} 件")
    log("=== 収集終了 ===\n")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
