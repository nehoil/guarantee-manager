#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_SITE = {"id", "name", "tagline", "returnPolicy"}
REQUIRED_ITEM = {"id", "title", "description", "category", "price", "vendor", "url", "image", "badges"}


def localized(value, field):
    if not isinstance(value, dict) or not value.get("he") or not value.get("en"):
        raise ValueError(f"{field} must contain he and en")


def main(path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = REQUIRED_SITE - set(data.get("site", {}))
    if missing:
        raise ValueError(f"site missing: {sorted(missing)}")
    for field in ["name", "tagline", "returnPolicy"]:
        localized(data["site"][field], f"site.{field}")
    ids = set()
    for item in data.get("items", []):
        missing = REQUIRED_ITEM - set(item)
        if missing:
            raise ValueError(f"item {item.get('id')} missing: {sorted(missing)}")
        if item["id"] in ids:
            raise ValueError(f"duplicate item id: {item['id']}")
        ids.add(item["id"])
        for field in ["title", "description", "category", "badges"]:
            localized(item[field], f"{item['id']}.{field}")
    print(f"OK: {len(data.get('items', []))} items")


if __name__ == "__main__":
    main(sys.argv[1])
