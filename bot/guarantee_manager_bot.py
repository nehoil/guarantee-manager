#!/usr/bin/env python3
"""Guarantee Manager Telegram CMS bot POC.

No third-party dependencies: uses Telegram Bot HTTP API directly.
Set TELEGRAM_BOT_TOKEN and ADMIN_TELEGRAM_ID before running.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "site" / "data" / "store.json"
USERS_PATH = ROOT / "data" / "users.json"

PERMISSIONS = {"create", "read", "update", "delete", "publish"}


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE env files without an extra dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(ROOT / ".env.local")
load_env_file(ROOT / ".env")


@dataclass
class User:
    telegram_id: str
    role: str
    pages: dict[str, set[str]]

    def can(self, page_id: str, permission: str) -> bool:
        if self.role == "admin":
            return True
        return permission in self.pages.get(page_id, set())


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bootstrap_users() -> dict[str, Any]:
    users = load_json(USERS_PATH, {"users": {}})
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if admin_id and admin_id not in users["users"]:
        users["users"][admin_id] = {"role": "admin", "pages": {"*": sorted(PERMISSIONS)}}
        save_json(USERS_PATH, users)
    return users


def get_user(users: dict[str, Any], telegram_id: str) -> User:
    raw = users.get("users", {}).get(telegram_id)
    if not raw:
        return User(telegram_id, "guest", {})
    pages = {page: set(perms) for page, perms in raw.get("pages", {}).items()}
    return User(telegram_id, raw.get("role", "guest"), pages)


def telegram(method: str, payload: dict[str, Any] | None = None) -> Any:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
    body = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send(chat_id: int, text: str) -> None:
    telegram("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})


def help_text(user: User) -> str:
    base = [
        "<b>Guarantee Manager</b>",
        "Send a product URL to draft an item.",
        "",
        "Manager commands:",
        "/list — show current items",
        "/addurl &lt;url&gt; — draft item from vendor link",
        "/publish &lt;draft_id&gt; — publish drafted item",
    ]
    if user.role == "admin":
        base += [
            "",
            "Admin commands:",
            "/addmanager &lt;telegram_id&gt; &lt;page_id&gt; &lt;create,read,update,delete,publish&gt;",
            "/removemanager &lt;telegram_id&gt;",
            "/permissions &lt;telegram_id&gt;",
        ]
    return "\n".join(base)


def add_manager(users: dict[str, Any], args: list[str]) -> str:
    if len(args) != 3:
        return "Usage: /addmanager <telegram_id> <page_id> <comma_permissions>"
    telegram_id, page_id, raw_permissions = args
    permissions = {p.strip() for p in raw_permissions.split(",") if p.strip()}
    invalid = permissions - PERMISSIONS
    if invalid:
        return f"Unknown permissions: {', '.join(sorted(invalid))}"
    users.setdefault("users", {})[telegram_id] = {
        "role": "manager",
        "pages": {page_id: sorted(permissions or {"read"})},
    }
    save_json(USERS_PATH, users)
    return f"Manager {telegram_id} can now {', '.join(sorted(permissions))} on {page_id}."


def remove_manager(users: dict[str, Any], args: list[str]) -> str:
    if len(args) != 1:
        return "Usage: /removemanager <telegram_id>"
    removed = users.setdefault("users", {}).pop(args[0], None)
    save_json(USERS_PATH, users)
    return "Removed." if removed else "No such manager."


def list_items() -> str:
    store = load_json(DATA_PATH, {})
    lines = [f"<b>{store.get('site', {}).get('id', 'site')}</b>"]
    for item in store.get("items", []):
        title = item.get("title", {}).get("en") or item.get("id")
        lines.append(f"• {item.get('id')} — {title}")
    return "\n".join(lines)


def enrich_url(url: str) -> dict[str, Any]:
    """Best-effort metadata fetch. Future hook: Tavily/LLM product normalization.

    AliExpress and some vendors aggressively block bots; when OG tags are missing we
    still create a draft with the URL so a manager can edit it manually.
    """
    title = urllib.parse.urlparse(url).netloc or "Vendor item"
    description = "Imported product draft. Review title, description, price and image before publishing."
    image = "assets/bottle.svg"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 GuaranteeManagerBot/0.1"})
        with urllib.request.urlopen(request, timeout=12) as response:
            html = response.read(500_000).decode("utf-8", errors="ignore")
        title = find_meta(html, "og:title") or find_title(html) or title
        description = find_meta(html, "og:description") or description
        image = find_meta(html, "og:image") or image
    except Exception:
        pass
    draft_id = f"draft-{int(time.time())}"
    return {
        "id": draft_id,
        "title": {"he": title, "en": title},
        "description": {"he": description, "en": description},
        "category": {"he": "חדש", "en": "New"},
        "price": "TBD",
        "rating": 4.5,
        "vendor": urllib.parse.urlparse(url).netloc,
        "url": url,
        "image": image,
        "badges": {"he": ["לבדיקה"], "en": ["Review"]},
        "status": "draft",
    }


def find_meta(html: str, property_name: str) -> str | None:
    pattern = rf'<meta[^>]+(?:property|name)=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def find_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


def add_url(user: User, args: list[str]) -> str:
    store = load_json(DATA_PATH, {})
    page_id = store.get("site", {}).get("id", "liors-guarantee")
    if not user.can(page_id, "create"):
        return "You do not have create permission for this page."
    if len(args) != 1 or not args[0].startswith(("http://", "https://")):
        return "Usage: /addurl <https://product-url>"
    draft = enrich_url(args[0])
    drafts_path = ROOT / "data" / "drafts.json"
    drafts = load_json(drafts_path, {"drafts": []})
    drafts["drafts"].append(draft)
    save_json(drafts_path, drafts)
    return f"Draft created: {draft['id']}\nTitle: {draft['title']['en']}\nPublish with /publish {draft['id']} after review."


def publish(user: User, args: list[str]) -> str:
    store = load_json(DATA_PATH, {})
    page_id = store.get("site", {}).get("id", "liors-guarantee")
    if not user.can(page_id, "publish"):
        return "You do not have publish permission for this page."
    if len(args) != 1:
        return "Usage: /publish <draft_id>"
    drafts_path = ROOT / "data" / "drafts.json"
    drafts = load_json(drafts_path, {"drafts": []})
    draft = next((d for d in drafts["drafts"] if d.get("id") == args[0]), None)
    if not draft:
        return "Draft not found."
    draft.pop("status", None)
    store.setdefault("items", []).insert(0, draft)
    drafts["drafts"] = [d for d in drafts["drafts"] if d.get("id") != args[0]]
    save_json(DATA_PATH, store)
    save_json(drafts_path, drafts)
    return f"Published {args[0]}. Next step: commit data/store.json to GitHub Pages repo."


def handle_message(update: dict[str, Any], users: dict[str, Any]) -> None:
    message = update.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    sender_id = str(message.get("from", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return
    user = get_user(users, sender_id)
    command, *args = text.split()
    if command in {"/start", "/help"}:
        send(chat_id, help_text(user))
    elif command == "/list":
        send(chat_id, list_items())
    elif command == "/addmanager" and user.role == "admin":
        send(chat_id, add_manager(users, args))
    elif command == "/removemanager" and user.role == "admin":
        send(chat_id, remove_manager(users, args))
    elif command == "/permissions" and user.role == "admin":
        target = args[0] if args else sender_id
        send(chat_id, json.dumps(users.get("users", {}).get(target, {}), ensure_ascii=False, indent=2))
    elif command == "/addurl" or text.startswith(("http://", "https://")):
        send(chat_id, add_url(user, args if command == "/addurl" else [text]))
    elif command == "/publish":
        send(chat_id, publish(user, args))
    else:
        send(chat_id, "Unknown command. Try /help")


def run_polling() -> None:
    users = bootstrap_users()
    offset = 0
    print("Guarantee Manager bot polling…", file=sys.stderr)
    while True:
        result = telegram("getUpdates", {"timeout": 25, "offset": offset})
        for update in result.get("result", []):
            offset = max(offset, update["update_id"] + 1)
            handle_message(update, users)


if __name__ == "__main__":
    run_polling()
