---
id: browser-navigation
name: Browser Navigation
description: Navigate to a URL or move between pages in the headless browser.
triggers:
  - go to
  - navigate to
  - open url
  - open website
  - open https
  - open http
  - visit
tags:
  - browser
  - web
  - navigation
priority: 10
---

For browser navigation:

1. Use `goto` with the full URL including the scheme (https://...).
2. Wait for `domcontentloaded` or `networkidle` if the page has heavy JS.
3. Verify by checking `get_url` and `get_title`.
4. If a link must be followed, prefer `text=Link Text` or `a[href*="path"]` selectors.
