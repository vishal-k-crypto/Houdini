---
id: save-file
name: Save a File
description: Save a file to a specific folder using the macOS Save dialog correctly.
triggers:
  - save
  - save as
  - save file
  - save to
tags:
  - macos
  - save dialog
  - file
priority: 10
---

When saving to a specific folder on macOS:

1. Open the Save dialog with **Cmd+S**.
2. Do NOT type the full path into the main filename field.
3. Press **Cmd+Shift+G** to open the "Go to Folder" dialog.
4. Type the target folder path (e.g. `~/Downloads/` or `/Users/<name>/Documents/`).
5. Press **Enter** to navigate there.
6. Type the filename (e.g. `report.txt`).
7. Press **Enter** to save.

Wait briefly between dialog transitions so the UI can settle.
