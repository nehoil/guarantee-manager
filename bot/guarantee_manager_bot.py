#!/usr/bin/env python3
"""Guarantee Manager Telegram CMS bot POC.

Dependency-free Telegram CMS bot for the Lior's Guarantee GitHub Pages site.

Flow:
1. Admin grants page manager permissions.
2. Manager sends a product URL.
3. Bot creates a metadata draft and shows inline actions.
4. Manager edits fields if needed.
5. Manager publishes draft into site/data/store.json.
6. Optional: /deploy commits + pushes the static site changes.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
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
DRAFTS_PATH = ROOT / "data" / "drafts.json"

PERMISSIONS = {"create", "read", "update", "delete", "publish"}
DEFAULT_PAGE_ID = "liors-guarantee"


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
        return permission in self.pages.get(page_id, set()) or permission in self.pages.get("*", set())


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def current_page_id() -> str:
    store = load_json(DATA_PATH, {})
    return store.get("site", {}).get("id", DEFAULT_PAGE_ID)


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


def esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


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
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.loads(response.read().decode("utf-8"))


def send(chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram("sendMessage", payload)


def edit_message(chat_id: int, message_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram("editMessageText", payload)


def answer_callback(callback_id: str, text: str = "") -> None:
    telegram("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def keyboard(rows: list[list[tuple[str, str]]]) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": text, "callback_data": data} for text, data in row] for row in rows]}


def main_menu_keyboard(user: User) -> dict[str, Any]:
    rows = [[("🛍️ Items", "list:items"), ("🧾 Drafts", "list:drafts")]]
    if user.role == "admin":
        rows.append([("👑 Admin help", "help:admin")])
    return keyboard(rows)


def help_text(user: User) -> str:
    base = [
        "<b>Guarantee Manager</b>",
        "Send me a product URL and I’ll create a draft for Lior’s Guarantee.",
        "",
        "<b>Manager commands</b>",
        "/list — show published items",
        "/drafts — show product drafts",
        "/addurl &lt;url&gt; — create draft from vendor link",
        "/set &lt;draft_id&gt; &lt;field&gt; &lt;value&gt; — edit a draft field",
        "/publish &lt;draft_id&gt; — publish a draft",
        "/setitem &lt;item_id&gt; &lt;field&gt; &lt;value&gt; — edit a live item locally",
        "/delete &lt;draft_id|item_id&gt; — delete draft/item if allowed",
        "/deploy — commit + push public site data changes",
        "",
        "Editable fields: title_he, title_en, desc_he, desc_en, category_he, category_en, price, rating, vendor, url, image, badges_he, badges_en",
    ]
    if user.role == "admin":
        base += [
            "",
            "<b>Admin commands</b>",
            "/addmanager &lt;telegram_id&gt; &lt;page_id&gt; &lt;create,read,update,delete,publish&gt;",
            "/removemanager &lt;telegram_id&gt;",
            "/permissions &lt;telegram_id&gt;",
            "",
            f"Current page: <code>{esc(current_page_id())}</code>",
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
    return f"Manager {esc(telegram_id)} can now {esc(', '.join(sorted(permissions)))} on {esc(page_id)}."


def remove_manager(users: dict[str, Any], args: list[str]) -> str:
    if len(args) != 1:
        return "Usage: /removemanager <telegram_id>"
    removed = users.setdefault("users", {}).pop(args[0], None)
    save_json(USERS_PATH, users)
    return "Removed." if removed else "No such manager."


def list_items() -> str:
    store = load_json(DATA_PATH, {})
    lines = [f"<b>{esc(store.get('site', {}).get('name', {}).get('en', 'Lior’s Guarantee'))}</b>", ""]
    for item in store.get("items", []):
        title = item.get("title", {}).get("en") or item.get("title", {}).get("he") or item.get("id")
        lines.append(f"• <code>{esc(item.get('id'))}</code> — {esc(title)} · {esc(item.get('price', ''))}")
    return "\n".join(lines).strip()


def list_drafts_text() -> str:
    drafts = load_json(DRAFTS_PATH, {"drafts": []}).get("drafts", [])
    if not drafts:
        return "No drafts yet. Send a product URL to create one."
    lines = ["<b>Drafts</b>", ""]
    for draft in drafts:
        title = draft.get("title", {}).get("en") or draft.get("id")
        lines.append(f"• <code>{esc(draft.get('id'))}</code> — {esc(title)} · {esc(draft.get('price', 'TBD'))}")
    return "\n".join(lines)


def draft_keyboard(draft_id: str, user: User) -> dict[str, Any]:
    page_id = current_page_id()
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    if user.can(page_id, "publish"):
        row.append(("✅ Publish", f"draft:publish:{draft_id}"))
    if user.can(page_id, "delete"):
        row.append(("🗑 Delete", f"draft:delete:{draft_id}"))
    if row:
        rows.append(row)
    rows.append([("🧾 Drafts", "list:drafts"), ("🛍️ Items", "list:items")])
    return keyboard(rows)


def draft_card(draft: dict[str, Any]) -> str:
    return "\n".join([
        "<b>Product draft</b>",
        f"ID: <code>{esc(draft.get('id'))}</code>",
        f"Title EN: {esc(draft.get('title', {}).get('en', ''))}",
        f"Title HE: {esc(draft.get('title', {}).get('he', ''))}",
        f"Price: {esc(draft.get('price', 'TBD'))}",
        f"Vendor: {esc(draft.get('vendor', ''))}",
        f"URL: {esc(draft.get('url', ''))}",
        "",
        "Edit example:",
        f"<code>/set {esc(draft.get('id'))} price $19</code>",
        f"<code>/set {esc(draft.get('id'))} title_he שם מוצר</code>",
    ])


def item_card(item: dict[str, Any]) -> str:
    return "\n".join([
        "<b>Published item</b>",
        f"ID: <code>{esc(item.get('id'))}</code>",
        f"Title: {esc(item.get('title', {}).get('en') or item.get('title', {}).get('he') or '')}",
        f"Price: {esc(item.get('price', ''))}",
        f"Vendor: {esc(item.get('vendor', ''))}",
        f"URL: {esc(item.get('url', ''))}",
    ])


def slugify(text: str) -> str:
    parsed = urllib.parse.urlparse(text)
    source = parsed.netloc + "-" + parsed.path if parsed.netloc else text
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    return (slug or f"item-{int(time.time())}")[:52]


def enrich_url(url: str) -> dict[str, Any]:
    """Best-effort metadata fetch. Future hook: Tavily/LLM product normalization."""
    parsed = urllib.parse.urlparse(url)
    title = parsed.netloc or "Vendor item"
    description = "Imported product draft. Review title, description, price and image before publishing."
    image = "assets/bottle.svg"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 GuaranteeManagerBot/0.2"})
        with urllib.request.urlopen(request, timeout=14) as response:
            html_text = response.read(700_000).decode("utf-8", errors="ignore")
        title = find_meta(html_text, "og:title") or find_meta(html_text, "twitter:title") or find_title(html_text) or title
        description = find_meta(html_text, "og:description") or find_meta(html_text, "description") or description
        image = find_meta(html_text, "og:image") or find_meta(html_text, "twitter:image") or image
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
        "vendor": parsed.netloc,
        "url": url,
        "image": image,
        "badges": {"he": ["לבדיקה"], "en": ["Review"]},
        "status": "draft",
        "createdAt": int(time.time()),
    }


def find_meta(html_text: str, property_name: str) -> str | None:
    # Supports content before/after property/name, double/single quotes, and noisy vendor markup.
    tag_re = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
    attr_re = re.compile(r"([a-zA-Z_:.-]+)\s*=\s*(['\"])(.*?)\2", re.DOTALL)
    for tag in tag_re.findall(html_text):
        attrs = {m.group(1).lower(): html.unescape(m.group(3).strip()) for m in attr_re.finditer(tag)}
        if attrs.get("property", "").lower() == property_name.lower() or attrs.get("name", "").lower() == property_name.lower():
            return attrs.get("content")
    return None


def find_title(html_text: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
    return html.unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else None


def create_draft(user: User, url: str) -> tuple[str, dict[str, Any] | None]:
    page_id = current_page_id()
    if not user.can(page_id, "create"):
        return "You do not have create permission for this page.", None
    if not url.startswith(("http://", "https://")):
        return "Send a valid product URL starting with http:// or https://", None
    draft = enrich_url(url)
    drafts = load_json(DRAFTS_PATH, {"drafts": []})
    drafts.setdefault("drafts", []).append(draft)
    save_json(DRAFTS_PATH, drafts)
    return "Draft created.", draft


def find_draft(draft_id: str) -> dict[str, Any] | None:
    return next((d for d in load_json(DRAFTS_PATH, {"drafts": []}).get("drafts", []) if d.get("id") == draft_id), None)


def apply_record_field(record: dict[str, Any], field: str, value: str) -> str | None:
    field_map = {
        "title_he": ("title", "he"),
        "title_en": ("title", "en"),
        "desc_he": ("description", "he"),
        "desc_en": ("description", "en"),
        "category_he": ("category", "he"),
        "category_en": ("category", "en"),
        "badges_he": ("badges", "he"),
        "badges_en": ("badges", "en"),
    }
    if field in field_map:
        parent, lang = field_map[field]
        record.setdefault(parent, {})[lang] = [v.strip() for v in value.split(",") if v.strip()] if parent == "badges" else value
    elif field in {"price", "vendor", "url", "image"}:
        record[field] = value
    elif field == "rating":
        try:
            record[field] = float(value)
        except ValueError:
            return "rating must be a number."
    else:
        return "Unknown field. Try /help for editable fields."
    return None


def set_draft_field(user: User, args: list[str]) -> str:
    page_id = current_page_id()
    if not user.can(page_id, "update"):
        return "You do not have update permission for this page."
    if len(args) < 3:
        return "Usage: /set <draft_id> <field> <value>"
    draft_id, field, value = args[0], args[1], " ".join(args[2:]).strip()
    drafts = load_json(DRAFTS_PATH, {"drafts": []})
    draft = next((d for d in drafts.get("drafts", []) if d.get("id") == draft_id), None)
    if not draft:
        return "Draft not found."
    error = apply_record_field(draft, field, value)
    if error:
        return error
    save_json(DRAFTS_PATH, drafts)
    return f"Updated draft {esc(field)} for <code>{esc(draft_id)}</code>."


def set_item_field(user: User, args: list[str]) -> str:
    page_id = current_page_id()
    if not user.can(page_id, "update"):
        return "You do not have update permission for this page."
    if len(args) < 3:
        return "Usage: /setitem <item_id> <field> <value>"
    item_id, field, value = args[0], args[1], " ".join(args[2:]).strip()
    store = load_json(DATA_PATH, {})
    item = next((i for i in store.get("items", []) if i.get("id") == item_id), None)
    if not item:
        return "Published item not found."
    error = apply_record_field(item, field, value)
    if error:
        return error
    save_json(DATA_PATH, store)
    return f"Updated live item {esc(field)} for <code>{esc(item_id)}</code> locally. Run /deploy to push it live."


def publish_draft(user: User, draft_id: str) -> str:
    page_id = current_page_id()
    if not user.can(page_id, "publish"):
        return "You do not have publish permission for this page."
    store = load_json(DATA_PATH, {})
    drafts = load_json(DRAFTS_PATH, {"drafts": []})
    draft = next((d for d in drafts.get("drafts", []) if d.get("id") == draft_id), None)
    if not draft:
        return "Draft not found."
    item = dict(draft)
    item.pop("status", None)
    item.pop("createdAt", None)
    base_id = slugify(item.get("title", {}).get("en") or item.get("url") or draft_id)
    existing_ids = {i.get("id") for i in store.get("items", [])}
    item_id = base_id
    suffix = 2
    while item_id in existing_ids:
        item_id = f"{base_id}-{suffix}"
        suffix += 1
    item["id"] = item_id
    store.setdefault("items", []).insert(0, item)
    drafts["drafts"] = [d for d in drafts.get("drafts", []) if d.get("id") != draft_id]
    save_json(DATA_PATH, store)
    save_json(DRAFTS_PATH, drafts)
    if os.getenv("AUTO_DEPLOY_ON_PUBLISH", "false").lower() == "true":
        deploy_result = deploy_changes(user, f"content: publish {item_id}")
        return f"Published <code>{esc(item_id)}</code>.\n\n{deploy_result}"
    return f"Published <code>{esc(item_id)}</code> locally. Run /deploy to push it live."


def delete_draft_or_item(user: User, target_id: str) -> str:
    page_id = current_page_id()
    if not user.can(page_id, "delete"):
        return "You do not have delete permission for this page."
    drafts = load_json(DRAFTS_PATH, {"drafts": []})
    before = len(drafts.get("drafts", []))
    drafts["drafts"] = [d for d in drafts.get("drafts", []) if d.get("id") != target_id]
    if len(drafts["drafts"]) != before:
        save_json(DRAFTS_PATH, drafts)
        return f"Deleted draft <code>{esc(target_id)}</code>."
    store = load_json(DATA_PATH, {})
    before = len(store.get("items", []))
    store["items"] = [i for i in store.get("items", []) if i.get("id") != target_id]
    if len(store["items"]) != before:
        save_json(DATA_PATH, store)
        return f"Deleted published item <code>{esc(target_id)}</code> locally. Run /deploy to push it live."
    return "Draft/item not found."


def deploy_changes(user: User, message: str = "content: update store items") -> str:
    page_id = current_page_id()
    if not user.can(page_id, "publish"):
        return "You do not have deploy permission for this page."
    status = subprocess.run(["git", "status", "--short", "site/data/store.json"], cwd=ROOT, text=True, capture_output=True, check=True)
    if not status.stdout.strip():
        return "No public site data changes to deploy."
    subprocess.run(["python3", "bot/validate_data.py", "site/data/store.json"], cwd=ROOT, check=True, text=True, capture_output=True)
    subprocess.run(["git", "add", "site/data/store.json"], cwd=ROOT, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True, capture_output=True, check=True)
    if not staged.stdout.strip():
        return "Only runtime draft data changed; nothing public to deploy."
    subprocess.run(["git", "commit", "-m", message], cwd=ROOT, check=True, text=True, capture_output=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True, text=True, capture_output=True)
    return "Deployed to GitHub. GitHub Pages will update in a moment."


def handle_callback(update: dict[str, Any], users: dict[str, Any]) -> None:
    query = update.get("callback_query") or {}
    callback_id = query.get("id")
    data = query.get("data", "")
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    sender_id = str(query.get("from", {}).get("id", ""))
    if not callback_id or not chat_id or not message_id:
        return
    user = get_user(users, sender_id)
    try:
        if data == "list:items":
            answer_callback(callback_id)
            edit_message(chat_id, message_id, list_items(), main_menu_keyboard(user))
        elif data == "list:drafts":
            answer_callback(callback_id)
            edit_message(chat_id, message_id, list_drafts_text(), main_menu_keyboard(user))
        elif data == "help:admin":
            answer_callback(callback_id)
            edit_message(chat_id, message_id, help_text(user), main_menu_keyboard(user))
        elif data.startswith("draft:publish:"):
            draft_id = data.split(":", 2)[2]
            answer_callback(callback_id, "Publishing…")
            edit_message(chat_id, message_id, publish_draft(user, draft_id), main_menu_keyboard(user))
        elif data.startswith("draft:delete:"):
            draft_id = data.split(":", 2)[2]
            answer_callback(callback_id, "Deleting…")
            edit_message(chat_id, message_id, delete_draft_or_item(user, draft_id), main_menu_keyboard(user))
        else:
            answer_callback(callback_id, "Unknown action")
    except Exception as exc:  # keep bot responsive during POC
        answer_callback(callback_id, "Error")
        send(chat_id, f"Error: <code>{esc(exc)}</code>")


def handle_message(update: dict[str, Any], users: dict[str, Any]) -> None:
    message = update.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    sender_id = str(message.get("from", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return
    user = get_user(users, sender_id)
    command, *args = text.split()
    try:
        if command in {"/start", "/help"}:
            send(chat_id, help_text(user), main_menu_keyboard(user))
        elif command == "/list":
            send(chat_id, list_items(), main_menu_keyboard(user))
        elif command == "/drafts":
            send(chat_id, list_drafts_text(), main_menu_keyboard(user))
        elif command == "/addmanager" and user.role == "admin":
            send(chat_id, add_manager(users, args))
        elif command == "/removemanager" and user.role == "admin":
            send(chat_id, remove_manager(users, args))
        elif command == "/permissions" and user.role == "admin":
            target = args[0] if args else sender_id
            send(chat_id, f"<pre>{esc(json.dumps(users.get('users', {}).get(target, {}), ensure_ascii=False, indent=2))}</pre>")
        elif command == "/addurl" or text.startswith(("http://", "https://")):
            url = args[0] if command == "/addurl" and args else text
            msg, draft = create_draft(user, url)
            send(chat_id, draft_card(draft) if draft else msg, draft_keyboard(draft["id"], user) if draft else None)
        elif command == "/set":
            send(chat_id, set_draft_field(user, args))
        elif command == "/publish":
            send(chat_id, publish_draft(user, args[0]) if args else "Usage: /publish <draft_id>", main_menu_keyboard(user))
        elif command == "/setitem":
            send(chat_id, set_item_field(user, args))
        elif command == "/delete":
            send(chat_id, delete_draft_or_item(user, args[0]) if args else "Usage: /delete <draft_id|item_id>", main_menu_keyboard(user))
        elif command == "/deploy":
            send(chat_id, deploy_changes(user), main_menu_keyboard(user))
        else:
            send(chat_id, "Unknown command. Try /help", main_menu_keyboard(user))
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr or exc.stdout or str(exc)
        send(chat_id, f"Command failed:\n<pre>{esc(detail[-3000:])}</pre>")
    except Exception as exc:
        send(chat_id, f"Error: <code>{esc(exc)}</code>")


def run_polling() -> None:
    users = bootstrap_users()
    offset = 0
    print("Guarantee Manager bot polling…", file=sys.stderr)
    while True:
        result = telegram("getUpdates", {"timeout": 25, "offset": offset})
        for update in result.get("result", []):
            offset = max(offset, update["update_id"] + 1)
            if "callback_query" in update:
                handle_callback(update, users)
            else:
                handle_message(update, users)


if __name__ == "__main__":
    run_polling()
