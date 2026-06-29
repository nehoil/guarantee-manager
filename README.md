# Guarantee Manager

Telegram CMS bot + GitHub Pages storefront POC.

Bot username: `@Guaranteecmsbot`.

First POC site: **Lior's Guarantee** — bilingual Hebrew/English list of value-for-money longevity items.

## Run locally

```bash
cd guarantee-manager
npm run validate
npm run site:serve
# open http://localhost:4173
```

## Bot POC

```bash
export TELEGRAM_BOT_TOKEN="..."
export ADMIN_TELEGRAM_ID="5031071610"
npm run bot:dev
```

Commands:

- `/help` — show role-aware commands
- `/list` — list published products
- `/drafts` — list drafts
- send any `https://...` URL — create a product draft
- `/addurl <url>` — create a product draft
- `/set <draft_id> <field> <value>` — edit draft fields
- `/publish <draft_id>` — publish draft into `site/data/store.json`
- `/setitem <item_id> <field> <value>` — edit a published item locally
- `/delete <draft_id|item_id>` — delete a draft or published item
- `/deploy` — validate, commit, and push public site data
- `/addmanager <telegram_id> <page_id> <create,read,update,delete,publish>`
- `/removemanager <telegram_id>`
- `/permissions <telegram_id>`

The bot also shows inline buttons for draft publish/delete and list navigation. Runtime files `data/users.json` and `data/drafts.json` are intentionally gitignored.

## Current status

- Storefront is static and GitHub Pages-friendly.
- i18n defaults to Hebrew.
- Light/dark mode included.
- Bot has RBAC + draft/publish skeleton.
- URL enrichment currently uses best-effort Open Graph scraping; Tavily/LLM adapter is the next step.
