---
id: browser-search
name: Browser Search
description: Search a website using the headless browser executor.
triggers:
  - search google
  - search bing
  - search the web
  - google for
  - look up online
tags:
  - browser
  - web
  - search
priority: 10
---

For browser-based searches:

1. Navigate to the search engine URL (e.g., https://www.google.com).
2. Click the search input if necessary.
3. Type the query.
4. Submit with Enter (`submit: true`).
5. Wait for results to load.
6. Extract the first result title or answer snippet with `get_clean_text`.

Prefer selectors like `[name="q"]` for Google or `#sb_form_q` for Bing.
