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

- `/help`
- `/list`
- `/addurl <url>`
- `/publish <draft_id>`
- `/addmanager <telegram_id> <page_id> <create,read,update,delete,publish>`
- `/removemanager <telegram_id>`
- `/permissions <telegram_id>`

## Current status

- Storefront is static and GitHub Pages-friendly.
- i18n defaults to Hebrew.
- Light/dark mode included.
- Bot has RBAC + draft/publish skeleton.
- URL enrichment currently uses best-effort Open Graph scraping; Tavily/LLM adapter is the next step.
