---
id: browser-form-fill
name: Browser Form Fill
description: Fill a web form field in the headless browser.
triggers:
  - fill form
  - fill in the form
  - fill out
  - enter name
  - enter email
  - type into field
  - form field
tags:
  - browser
  - web
  - form
priority: 10
---

For filling web forms:

1. Navigate to the form page.
2. Identify the target field by label text, placeholder, or input name.
3. Click the field to ensure focus.
4. Type the value.
5. If the task only asks to fill one field, verify with `get_clean_text` or a selector check.

Common selectors:
- `[placeholder="Customer name"]`
- `input[name="customer_name"]`
- `text=Customer name` then nearest input
