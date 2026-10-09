#!/usr/bin/env python3
"""Apple整備済製品ストア（日本）の在庫を確認し、対象モデルが入荷したら通知する。

通知先:
  1. ntfy.sh（環境変数 NTFY_TOPIC があれば、そのトピックへプッシュ通知）
  2. GitHub Issue（リポジトリ所有者を担当者にして Issue を作成 → GitHub からメール通知が届く）
状態は state.json に保存し、「なし→あり」に変わった時だけ通知する。
"""
import datetime
import json
import os
import re
import sys
import urllib.request

URL = "https://www.apple.com/jp/shop/refurbished/iphone/iphone-15-pro"
# 監視対象（Appleのページ内部で使われている絞り込みキー）
TARGET = {
    "refurbClearModel": "iphone15pro",
    "dimensionCapacity": "256gb",
    "dimensionColor": "whitetitanium",
}
LABEL = "iPhone 15 Pro 256GB ホワイトチタニウム（整備済製品）"
STATE_FILE = "state.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
JST = datetime.timezone(datetime.timedelta(hours=9))


def now():
    return datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")


def today():
    return datetime.datetime.now(JST).strftime("%Y-%m-%d")


def fetch_tiles():
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r"REFURB_GRID_BOOTSTRAP\s*=\s*", html)
    if not m:
        raise RuntimeError("REFURB_GRID_BOOTSTRAP が見つからない（ページ構造が変わった？）")
    obj, _ = json.JSONDecoder().raw_decode(html, m.end())
    return obj["tiles"]


def find_target(tiles):
    hits = []
    for t in tiles:
        dims = (t.get("filters") or {}).get("dimensions") or {}
        if all(dims.get(k) == v for k, v in TARGET.items()):
            hits.append(t)
    return hits


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def notify_ntfy(title, message, click=None, priority=4):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC 未設定のため ntfy 通知はスキップ")
        return
    body = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": ["iphone"]}
    if click:
        body["click"] = click
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        print("ntfy:", r.status)


def gh_api(method, path, data=None):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print(f"GITHUB_TOKEN/GITHUB_REPOSITORY 未設定のため Issue 操作はスキップ: {method} {path}")
        return {}
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def owner():
    return os.environ.get("GITHUB_REPOSITORY_OWNER", "")


def new_issue(title, body):
    data = {"title": title, "body": f"@{owner()}\n\n{body}" if owner() else body}
    if owner():
        data["assignees"] = [owner()]
    return gh_api("POST", "/issues", data)


def product_url(tile):
    return "https://www.apple.com" + tile["productDetailsUrl"].split("?")[0]


def main():
    state = load_state()
    state.setdefault("in_stock", False)
    state.setdefault("parts", [])
    state.setdefault("errors", 0)

    if os.environ.get("TEST_NOTIFY") == "true":
        print("テスト通知を送信")
        notify_ntfy("テスト通知: 在庫監視が動いています", f"{LABEL}\n{now()} 時点では在庫なし。入荷したらこの形で通知します。", click=URL)
        issue = new_issue("テスト通知（在庫監視の動作確認）",
                          f"{now()}\n\n{LABEL} の監視が動いています。入荷すると同じ形で Issue が立ち、メールが届きます。")
        print("テスト Issue:", issue.get("html_url"))

    try:
        tiles = fetch_tiles()
    except Exception as e:  # ページ取得・解析の失敗
        state["errors"] += 1
        state["last_error"] = f"{now()} {e}"
        save_state(state)
        print("取得失敗:", e)
        # 最初の失敗と、その後は失敗が続く間 1日1回だけ run を失敗させてメールで知らせる
        if state["errors"] == 1 or state["errors"] % 48 == 0:
            sys.exit(1)
        return

    hits = find_target(tiles)
    in_stock = bool(hits)
    parts = sorted(h["partNumber"] for h in hits)
    price = hits[0]["price"]["currentPrice"]["amount"] if hits else None
    link = product_url(hits[0]) if hits else URL
    print(f"{now()} tiles={len(tiles)} target_hits={len(hits)} parts={parts} price={price}")

    state["errors"] = 0
    state.pop("last_error", None)
    state["last_checked_date"] = today()

    if in_stock and (not state["in_stock"] or parts != state["parts"]):
        print("入荷を検知 → 通知")
        notify_ntfy(f"在庫あり {price}: {LABEL}", f"{now()} 確認\n{link}", click=link, priority=5)
        issue = new_issue(f"🟢 在庫あり {price} — {LABEL}",
                          f"{now()} に在庫を確認しました。\n\n**{price}**\n\n{link}\n\n(部品番号: {', '.join(parts)})")
        state["issue"] = issue.get("number")
        state["last_changed"] = now()
    elif not in_stock and state["in_stock"]:
        print("売り切れを検知")
        if state.get("issue"):
            gh_api("POST", f"/issues/{state['issue']}/comments", {"body": f"{now()} 売り切れを確認したのでクローズします。"})
            gh_api("PATCH", f"/issues/{state['issue']}", {"state": "closed"})
        notify_ntfy(f"売り切れ: {LABEL}", f"{now()} 一覧から消えました。", click=URL, priority=2)
        state["issue"] = None
        state["last_changed"] = now()

    state["in_stock"] = in_stock
    state["parts"] = parts
    state["price"] = price
    if in_stock:
        state["last_seen"] = now()
    save_state(state)


if __name__ == "__main__":
    main()
