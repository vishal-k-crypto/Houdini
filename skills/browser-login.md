---
id: browser-login
name: Browser Login
description: Log in to a website using the headless browser executor.
triggers:
  - log in
  - login to
  - sign in
  - signin to
  - authenticate
tags:
  - browser
  - web
  - login
  - auth
priority: 10
---

For logging into a website:

1. Navigate to the login page URL.
2. Identify the username/email field (selector hints: `input[type="email"]`, `input[name="username"]`, `input[name="email"]`).
3. Type the username/email.
4. Identify the password field (`input[type="password"]`).
5. Type the password.
6. Click the submit/sign-in button.
7. Wait for navigation or dashboard indicator.
8. Verify success by checking URL or presence of a logged-in element.

Never log in to sensitive accounts unless explicitly instructed. Prefer test/demo credentials.
