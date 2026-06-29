# Guarantee Manager — POC Spec

## Naming fixes

- Bot/product: **Guarantee Manager**
- First page: **Lior's Guarantee** / **האחריות של ליאור**
- Typo standardization: `guarantee` everywhere in English UI and code.

## Goal

A generic Telegram CMS bot for simple GitHub Pages storefront/list pages. Each page is a curated list of items with bilingual content, playful longevity design, theme toggle, and a visible money-back guarantee promise.

## Roles

### Bot admin

Initial admin: Telegram ID `5031071610`.

Can:

- Add/remove page managers.
- Grant/revoke CRUD permissions per page.
- View permissions.
- Eventually connect a page to a GitHub repository/branch.

### Page manager

Can, depending on granted permissions:

- Create product drafts from URLs.
- Read/list current items.
- Update product copy/metadata.
- Delete items or drafts.
- Publish approved drafts.

## Data flow

1. Manager sends a vendor URL, e.g. AliExpress/Amazon/other shop.
2. Bot fetches basic metadata from Open Graph/title tags.
3. Future enrichment step: Tavily/search + LLM transforms messy vendor data into clean bilingual product copy.
4. Manager reviews/edits draft.
5. Manager publishes.
6. Bot commits updated `site/data/store.json` to the GitHub Pages repo.

## Storefront features in this POC

- Static GitHub Pages-compatible site.
- Hebrew default with RTL layout.
- English/Hebrew i18n toggle.
- Light/dark theme toggle.
- Playful, happy color palette inspired by colorful GitHub profile/repo card energy, with a longevity/wellness direction.
- Large money-back guarantee badge and one-line return policy.

## Future production pieces

- Real Telegram webhook deployment instead of long polling.
- GitHub App or PAT-based commits.
- Safer vendor scraping queue with retries/rate limits.
- Real LLM/Tavily enrichment provider adapter.
- Admin approval flow before publishing.
- Multi-page routing and per-page GitHub Pages deployment config.
