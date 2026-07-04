# Houdini Agent — Skill Protocol

Houdini uses a **skill-as-file** protocol to inject reusable, versioned task instructions into the planner. This lets the agent handle common task families more reliably without reasoning from scratch every time.

The protocol is inspired by [Open Design](https://github.com/nexu-io/open-design)'s `SKILL.md` files.

---

## What is a skill?

A skill is a Markdown file with YAML frontmatter that describes:

- **What** task family it covers
- **When** to apply it (trigger keywords)
- **How** to execute it (detailed instructions)

Skills are loaded at runtime from `skills/` and matched against the user's task. Matching skills are appended to the planner's system prompt.

---

## File format

```markdown
---
id: open-app
name: Open an Application
description: Quickly open any macOS application using Spotlight or the Dock.
triggers:
  - open
  - launch
  - start
  - open app
tags:
  - macos
  - spotlight
  - launch
priority: 10
---

When the user asks to open an application, use the fastest path:

1. Press **Cmd+Space** to open Spotlight.
2. Type the exact application name (e.g. "Safari", "Calculator", "Notes").
3. Press **Enter** to launch it.
4. Wait briefly for the app to appear before proceeding.
```

### Frontmatter fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | No | Unique identifier. Defaults to the filename stem. |
| `name` | No | Human-readable name. Defaults to a title-cased `id`. |
| `description` | No | Short summary shown in the frontend and logs. |
| `triggers` | No | Keywords/phrases that activate the skill. Partial matches in the task text score highly. |
| `tags` | No | Categories used for token-overlap matching. |
| `priority` | No | Integer. Higher values sort first and get a small score boost. |
| `metadata` | No | Free-form dict for future extensions. |

The Markdown body after the frontmatter is the actual instruction text injected into the planner.

---

## Where skills are loaded from

Default search paths (in priority order):

1. `./skills/` — project skills (shipped with Houdini)
2. `~/.config/houdini/skills/` — user skills

You can also load from custom directories programmatically:

```python
from src.skills import SkillRegistry

registry = SkillRegistry.from_directories(["/path/to/skills"])
```

---

## How matching works

The registry scores each skill against the task using a lightweight keyword model:

- **Trigger match**: +2.0 per trigger found in the task; +1.0 extra if the task starts with the trigger.
- **Token overlap**: up to +1.5 based on shared tokens between the task and the skill's name/description/tags/triggers.
- **Priority**: +0.1 × priority.

Only skills with a score ≥ 1.0 are injected, and the planner receives at most the top 2 by default.

You can test matching with the API:

```bash
curl "http://localhost:8420/api/skills?task=open+Safari+and+search+Python"
```

Or in the frontend at **Skills**.

---

## Adding a custom skill

1. Create a new Markdown file in `skills/` or `~/.config/houdini/skills/`.
2. Add YAML frontmatter and Markdown instructions.
3. Restart the Houdini daemon to reload skills.
4. Test the match in the frontend or via `/api/skills?task=...`.

### Example: "compose-email"

```markdown
---
id: compose-email
name: Compose an Email
description: Write and send an email in Apple Mail or Gmail.
triggers:
  - email
  - send email
  - compose email
tags:
  - mail
  - gmail
priority: 10
---

For Apple Mail:
1. Open Mail with Cmd+Space.
2. Press Cmd+N to start a new message.
3. Tab to the To field and type the recipient.
4. Tab to Subject, type the subject.
5. Tab to the body, type the message.
6. Press Cmd+Enter to send.
```

---

## Programmatic usage

```python
from src.skills import skill_registry

# List all skills
for skill in skill_registry.skills:
    print(skill.id, skill.name)

# Get prompt fragment for a task
prompt_fragment = skill_registry.prompt_for_task("save the report to Downloads")
print(prompt_fragment)
```

---

## Tips for effective skills

- **Be concrete**: Prefer exact keyboard shortcuts and UI element names.
- **Target clickable elements**: When describing clicks, name the button/link, not the surrounding text.
- **Keep it focused**: One skill per task family. Long generic instructions dilute the signal.
- **Use triggers wisely**: Short, distinctive phrases work better than single common words.
- **Version control**: Keep skills in Git so you can iterate and review them.
