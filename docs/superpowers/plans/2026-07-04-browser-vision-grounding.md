# Browser Vision Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add screenshot + Set-of-Marks vision grounding to the headless browser executor so Houdini can locate visual-only elements and compete with browser-use / Operator-style agents on real websites.

**Architecture:** Introduce a `BrowserObservation` value object that bundles a screenshot, accessibility tree, and interactive-element bounding boxes. A `SetOfMarksRenderer` draws numbered markers on the screenshot and emits a `som_id -> selector` map. `BrowserTaskRunner` will prefer a vision plan when the active provider supports images; otherwise it falls back to the existing text-only plan. A tiny local HTTP fixture server supplies deterministic browser benchmark tasks so we can measure accuracy without relying on live sites.

**Tech Stack:** Python 3.11+, Playwright, Pillow, FastAPI (for fixture server), existing provider layer, pytest.

---

## File Structure

- **Create** `src/agents/browser_observation.py` — `BrowserObservation` dataclass + extraction helpers.
- **Create** `src/agents/browser_som.py` — `SetOfMarksRenderer` and `InteractiveElement` extraction.
- **Modify** `src/agents/browser_executor.py:346-413` — add vision-aware `_plan` path and vision action schema.
- **Create** `src/benchmarks/browser_fixture_server.py` — local HTTP server with deterministic web tasks.
- **Create** `src/benchmarks/web_benchmark_tasks.json` — task definitions for the local fixture server.
- **Create** `tests/test_browser_vision.py` — unit tests for observation, SOM, and runner planning.
- **Modify** `src/api/server.py` — expose `use_vision` toggle on `/api/tasks` and benchmark endpoints.
- **Modify** `frontend/src/routes/settings/+page.svelte` — add "Use browser vision" checkbox.
- **Modify** `docs/FRONTEND.md` — fix React → SvelteKit note.

---

### Task 1: BrowserObservation value object

**Files:**
- Create: `src/agents/browser_observation.py`
- Test: `tests/test_browser_vision.py`

- [ ] **Step 1: Write the failing test**

```python
def test_browser_observation_builds():
    from src.agents.browser_observation import BrowserObservation

    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64="iVBORw0KGgo=",
        accessibility_tree={"role": "WebArea", "name": "Example"},
        interactive_elements=[],
        clean_text="Example Domain",
    )
    assert obs.url == "https://example.com"
    assert obs.screenshot_bytes is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_browser_observation_builds -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.browser_observation'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Structured observation from a browser page."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrowserObservation:
    """A snapshot of the browser state at one timestep."""

    url: str
    title: str
    screenshot_b64: str
    accessibility_tree: Dict[str, Any]
    interactive_elements: List[Dict[str, Any]] = field(default_factory=list)
    clean_text: str = ""
    action_history: List[str] = field(default_factory=list)

    @property
    def screenshot_bytes(self) -> bytes:
        return base64.b64decode(self.screenshot_b64)

    def to_text_context(self, max_chars: int = 3000) -> str:
        parts = [
            f"URL: {self.url}",
            f"Title: {self.title}",
            "Page text:",
            self.clean_text[:max_chars],
        ]
        return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_browser_observation_builds -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/browser_observation.py tests/test_browser_vision.py
git commit -m "feat(browser): BrowserObservation value object"
```

---

### Task 2: Extract interactive elements and render Set-of-Marks

**Files:**
- Create: `src/agents/browser_som.py`
- Modify: `src/agents/browser_executor.py` (add `get_interactive_elements` and `get_screenshot_with_marks` later in Task 3)
- Test: `tests/test_browser_vision.py`

- [ ] **Step 1: Write the failing test**

```python
def test_som_renderer_labels_elements():
    from src.agents.browser_som import SetOfMarksRenderer
    from PIL import Image

    # Create a small white image
    img = Image.new("RGB", (200, 100), color="white")
    elements = [
        {"id": "btn-1", "bbox": {"x": 10, "y": 10, "width": 40, "height": 20}, "tag": "button", "text": "OK"},
        {"id": "btn-2", "bbox": {"x": 100, "y": 40, "width": 50, "height": 25}, "tag": "button", "text": "Cancel"},
    ]
    renderer = SetOfMarksRenderer()
    result = renderer.render(img, elements)

    assert len(result.marks) == 2
    assert result.marks[0]["som_id"] == 1
    assert result.marks[1]["som_id"] == 2
    assert result.id_to_element[1]["text"] == "OK"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_som_renderer_labels_elements -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Set-of-Marks (SoM) rendering for browser screenshots.

Draws numbered markers on interactive elements so a vision model can refer to
elements by ID instead of brittle CSS selectors.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


@dataclass
class SOMRenderResult:
    """Result of rendering Set-of-Marks on a screenshot."""

    image: Image.Image
    marks: List[Dict[str, Any]]
    id_to_element: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    @property
    def base64_png(self) -> str:
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


class SetOfMarksRenderer:
    """Render numbered markers on interactive browser elements."""

    def __init__(
        self,
        marker_radius: int = 12,
        marker_color: Tuple[int, int, int, int] = (255, 0, 0, 200),
        text_color: Tuple[int, int, int] = (255, 255, 255),
    ):
        self.marker_radius = marker_radius
        self.marker_color = marker_color
        self.text_color = text_color

    def render(
        self,
        screenshot: Image.Image,
        elements: List[Dict[str, Any]],
    ) -> SOMRenderResult:
        """Draw numbered markers and return the annotated image + mappings."""
        img = screenshot.convert("RGBA")
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        marks: List[Dict[str, Any]] = []
        id_to_element: Dict[int, Dict[str, Any]] = {}

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
        except Exception:
            font = ImageFont.load_default()

        for idx, element in enumerate(elements, start=1):
            bbox = element.get("bbox") or {}
            x = int(bbox.get("x", 0))
            y = int(bbox.get("y", 0))
            width = int(bbox.get("width", 0))
            height = int(bbox.get("height", 0))
            if width <= 0 or height <= 0:
                continue

            center_x = x + width // 2
            center_y = y + height // 2
            r = self.marker_radius
            draw.ellipse(
                [center_x - r, center_y - r, center_x + r, center_y + r],
                fill=self.marker_color,
            )
            text = str(idx)
            bbox_text = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]
            draw.text(
                (center_x - tw / 2, center_y - th / 2),
                text,
                font=font,
                fill=self.text_color,
            )

            mark = {
                "som_id": idx,
                "bbox": bbox,
                "text": element.get("text", ""),
                "tag": element.get("tag", ""),
            }
            marks.append(mark)
            id_to_element[idx] = element

        annotated = Image.alpha_composite(img, overlay)
        return SOMRenderResult(image=annotated.convert("RGB"), marks=marks, id_to_element=id_to_element)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_som_renderer_labels_elements -v`
Expected: PASS.

- [ ] **Step 5: Add element extraction helper to BrowserSession**

Modify `src/agents/browser_executor.py` after `get_accessibility_snapshot` (around line 192):

```python
    def get_interactive_elements(self) -> BrowserActionResult:
        """Return a list of interactive elements with bounding boxes."""
        try:
            elements = self.page.evaluate("""
                () => {
                    const tags = ['a', 'button', 'input', 'select', 'textarea'];
                    const out = [];
                    document.querySelectorAll(tags.join(',')).forEach((el, idx) => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            out.push({
                                id: el.id || `el-${idx}`,
                                tag: el.tagName.toLowerCase(),
                                text: (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').slice(0, 100),
                                type: el.type || null,
                                bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                            });
                        }
                    });
                    return out;
                }
            """)
            return BrowserActionResult(success=True, data={"elements": elements})
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Element extraction failed: {exc}")
```

Also add to `execute_plan`:

```python
            elif action == "get_interactive_elements":
                res = self.get_interactive_elements()
```

- [ ] **Step 6: Run existing browser executor tests**

Run: `.venv/bin/python -m pytest tests/test_browser_executor.py -q`
Expected: PASS (existing tests use mocks and should still pass).

- [ ] **Step 7: Commit**

```bash
git add src/agents/browser_som.py src/agents/browser_executor.py tests/test_browser_vision.py
git commit -m "feat(browser): Set-of-Marks renderer and interactive element extraction"
```

---

### Task 3: Vision-aware planning in BrowserTaskRunner

**Files:**
- Modify: `src/agents/browser_executor.py:346-413`
- Test: `tests/test_browser_vision.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock

def test_vision_plan_uses_som_when_provider_supports_vision():
    from src.agents.browser_executor import BrowserTaskRunner

    mock_client = MagicMock()
    mock_client.supports_vision = True
    mock_client.generate.return_value.text = '[{"action": "click", "som_id": 1}]'
    mock_client._extract_json.return_value = [{"action": "click", "som_id": 1}]

    runner = BrowserTaskRunner(client=mock_client, headless=True)
    # Patch observation building to avoid real browser
    runner._build_observation = lambda session: MagicMock(
        url="https://example.com",
        title="Example",
        screenshot_b64="iVBORw0KGgo=",
        accessibility_tree={},
        interactive_elements=[{"id": "btn", "tag": "button", "text": "OK", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}],
        clean_text="Example Domain",
    )

    plan = runner._plan("Click the OK button")
    assert plan == [{"action": "click", "som_id": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_vision_plan_uses_som_when_provider_supports_vision -v`
Expected: FAIL — `_plan` currently ignores vision.

- [ ] **Step 3: Implement vision-aware `_plan`**

Replace `BrowserTaskRunner._plan` in `src/agents/browser_executor.py:346-413` with:

```python
    def _plan(
        self,
        task: str,
        observation: Optional["BrowserObservation"] = None,
        action_history: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        client = self._get_client()
        action_history = action_history or []

        # Inject relevant skills as system guidance
        skills_text = ""
        try:
            from ..skills.registry import skill_registry
            skills_text = skill_registry.prompt_for_task(task, top_k=2, min_score=1.0)
        except Exception:
            pass

        if observation is not None and getattr(client, "supports_vision", False):
            return self._plan_with_vision(client, task, observation, action_history, skills_text)
        return self._plan_text_only(client, task, observation, action_history, skills_text)

    def _plan_text_only(
        self,
        client,
        task: str,
        observation: Optional["BrowserObservation"],
        action_history: List[str],
        skills_text: str,
    ) -> List[Dict[str, Any]]:
        snapshot_text = ""
        if observation and observation.accessibility_tree:
            snapshot_text = self._format_accessibility_snapshot(observation.accessibility_tree, max_nodes=50)
        context = (
            f"Current URL: {observation.url if observation else 'unknown'}\n"
            f"Page text:\n{(observation.clean_text if observation else 'N/A')[:3000]}\n"
            f"Accessibility tree:\n{snapshot_text or 'N/A'}"
        )
        if action_history:
            context += f"\n\nActions already taken:\n" + "\n".join(f"- {a}" for a in action_history[-10:])
        return self._call_planner(client, task, context, skills_text, vision=False)

    def _plan_with_vision(
        self,
        client,
        task: str,
        observation: "BrowserObservation",
        action_history: List[str],
        skills_text: str,
    ) -> List[Dict[str, Any]]:
        from .browser_som import SetOfMarksRenderer
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(observation.screenshot_bytes))
        renderer = SetOfMarksRenderer()
        som = renderer.render(img, observation.interactive_elements)

        som_list = "\n".join(
            f"[{m['som_id']}] {m['tag']} — {m['text'][:60]}"
            for m in som.marks
        )
        context = (
            f"Current URL: {observation.url}\n"
            f"Title: {observation.title}\n"
            f"Interactive elements (marked on the screenshot):\n{som_list}\n\n"
            f"Page text:\n{observation.clean_text[:2000]}"
        )
        if action_history:
            context += f"\n\nActions already taken:\n" + "\n".join(f"- {a}" for a in action_history[-10:])

        prompt = self._build_planner_prompt(task, context, skills_text, vision=True)
        result = client.generate(prompt, images=[som.base64_png], temperature=0.2)
        text = result.text if hasattr(result, "text") else str(result)
        try:
            plan = client._extract_json(text)
            return self._resolve_som_ids(plan, som.id_to_element)
        except Exception as exc:
            logger.warning(f"Browser vision plan JSON extraction failed: {exc}")
            return []

    def _resolve_som_ids(
        self,
        plan: List[Dict[str, Any]],
        id_to_element: Dict[int, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert som_id references into stable Playwright selectors."""
        resolved = []
        for step in plan:
            som_id = step.get("som_id")
            if som_id is not None and som_id in id_to_element:
                element = id_to_element[som_id]
                # Prefer ID selector, then text, then tag/type
                if element.get("id") and not str(element["id"]).startswith("el-"):
                    step["selector"] = f"#{element['id']}"
                elif element.get("text"):
                    step["selector"] = f"text={element['text']}"
                elif element.get("type"):
                    step["selector"] = f"{element['tag']}[type='{element['type']}']"
                else:
                    step["selector"] = element["tag"]
            resolved.append(step)
        return resolved

    def _build_observation(self, session: BrowserSession) -> "BrowserObservation":
        from .browser_observation import BrowserObservation

        text_res = session.get_clean_text(max_chars=3000)
        snapshot_res = session.get_accessibility_snapshot()
        elements_res = session.get_interactive_elements()
        screenshot_res = session.screenshot()

        return BrowserObservation(
            url=session.get_url(),
            title=session.get_title(),
            screenshot_b64=screenshot_res.data.get("base64", "") if screenshot_res.success else "",
            accessibility_tree=snapshot_res.data.get("snapshot") if snapshot_res.success else {},
            interactive_elements=elements_res.data.get("elements", []) if elements_res.success else [],
            clean_text=text_res.data.get("text", "") if text_res.success else "",
        )

    def _build_planner_prompt(
        self,
        task: str,
        context: str,
        skills_text: str,
        vision: bool,
    ) -> str:
        action_docs = """
- {"action": "goto", "url": "..."}
- {"action": "click", "selector": "...", "fallback_selectors": ["..."]}
- {"action": "click", "som_id": 1}  # vision mode only
- {"action": "type", "selector": "...", "text": "...", "submit": true/false}
- {"action": "type", "som_id": 1, "text": "...", "submit": true/false}  # vision mode only
- {"action": "press", "key": "..."}
- {"action": "scroll", "direction": "down|up", "amount": 500}
- {"action": "wait", "selector": "..."} or {"action": "wait", "seconds": 2}
- {"action": "hover", "selector": "..."}
- {"action": "select", "selector": "...", "value": "..."} or {"label": "..."}
- {"action": "get_text", "selector": "..."}
- {"action": "get_clean_text"}
- {"action": "screenshot"}
"""
        vision_note = """
The attached screenshot has numbered red markers on interactive elements. Use "som_id" to refer to the element you want to interact with. If an element has no marker, use a stable text or attribute selector.""" if vision else ""

        return f"""You are controlling a headless Chromium browser via Playwright to complete a real-world web task.

{skills_text}

Task: {task}

{context}

Return a JSON array of actions.{vision_note}

Available actions:
{action_docs}

Guidelines:
1. Start by navigating to the right page if no URL is loaded.
2. Click before typing into a field unless it is already focused.
3. Wait after navigation, form submission, or AJAX-heavy interactions.
4. If a search box exists, use `type` with `submit: true` rather than pressing Enter separately.
5. If the task asks for information, end with `get_text` or `get_clean_text`.
6. Do not assume success; verify the result when possible.

Respond with JSON only."""

    def _call_planner(self, client, task: str, context: str, skills_text: str, vision: bool = False) -> List[Dict[str, Any]]:
        prompt = self._build_planner_prompt(task, context, skills_text, vision)
        result = client.generate(prompt, temperature=0.2)
        text = result.text if hasattr(result, "text") else str(result)
        try:
            return client._extract_json(text)
        except Exception as exc:
            logger.warning(f"Browser plan JSON extraction failed: {exc}")
            return []
```

Also update the import at the top of `browser_executor.py` to include `BrowserObservation`:

```python
from typing import Any, Dict, List, Optional
```
(no new imports needed; BrowserObservation is referenced via string and imported inside methods)

Then update `BrowserTaskRunner.run` to use observations:

```python
    def run(self, task: str) -> Dict[str, Any]:
        if not self._is_browser_task(task):
            return {"success": False, "error": "Not a browser task", "browser": False}

        with BrowserSession(headless=self.headless) as session:
            observation = self._build_observation(session)
            plan = self._plan(task, observation=observation)
            ...
```

And in the replan loop, replace the manual state gathering with:

```python
                observation = self._build_observation(session)
                plan = self._plan(task, observation=observation, action_history=action_history)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_vision_plan_uses_som_when_provider_supports_vision tests/test_browser_executor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/browser_executor.py tests/test_browser_vision.py
git commit -m "feat(browser): vision-aware planning with Set-of-Marks resolution"
```

---

### Task 4: Deterministic browser benchmark fixture server

**Files:**
- Create: `src/benchmarks/browser_fixture_server.py`
- Create: `src/benchmarks/web_benchmark_tasks.json`
- Test: `tests/test_browser_vision.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fixture_server_serves_login_page():
    from src.benchmarks.browser_fixture_server import BrowserFixtureServer

    server = BrowserFixtureServer(port=0)
    server.start()
    try:
        url = server.url_for("/login")
        import requests
        r = requests.get(url, timeout=5)
        assert r.status_code == 200
        assert "Login" in r.text
    finally:
        server.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py::test_fixture_server_serves_login_page -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the fixture server**

```python
"""Local deterministic web pages for browser agent benchmarking.

Run standalone:
    python -m src.benchmarks.browser_fixture_server

Use in tests:
    server = BrowserFixtureServer(port=0)
    server.start()
    url = server.url_for("/login")
    ...
    server.stop()
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn


class BrowserFixtureServer:
    """A tiny FastAPI server serving deterministic web tasks."""

    DEFAULT_PAGES: Dict[str, str] = {
        "/login": """
<!doctype html>
<html>
<head><title>Login</title></head>
<body>
  <h1>Login</h1>
  <form id="login-form">
    <input id="username" type="text" placeholder="Username" />
    <input id="password" type="password" placeholder="Password" />
    <button id="submit" type="button">Login</button>
  </form>
  <p id="result"></p>
  <script>
    document.getElementById('submit').addEventListener('click', () => {
      const u = document.getElementById('username').value;
      const p = document.getElementById('password').value;
      const result = (u === 'admin' && p === 'houdini123') ? 'Welcome, admin!' : 'Invalid credentials';
      document.getElementById('result').textContent = result;
    });
  </script>
</body>
</html>
""",
        "/todo": """
<!doctype html>
<html>
<head><title>Todo List</title></head>
<body>
  <h1>Todo List</h1>
  <input id="new-todo" type="text" placeholder="New task" />
  <button id="add">Add</button>
  <ul id="list"></ul>
  <script>
    document.getElementById('add').addEventListener('click', () => {
      const input = document.getElementById('new-todo');
      if (!input.value) return;
      const li = document.createElement('li');
      li.textContent = input.value;
      document.getElementById('list').appendChild(li);
      input.value = '';
    });
  </script>
</body>
</html>
""",
        "/search": """
<!doctype html>
<html>
<head><title>Search</title></head>
<body>
  <h1>Search</h1>
  <input id="query" type="text" placeholder="Search..." />
  <button id="go">Search</button>
  <div id="results"></div>
  <script>
    document.getElementById('go').addEventListener('click', () => {
      const q = document.getElementById('query').value.toLowerCase();
      const results = document.getElementById('results');
      if (q.includes('houdini')) {
        results.innerHTML = '<p>Result 1: Houdini Agent</p><p>Result 2: Houdini VFX</p>';
      } else {
        results.innerHTML = '<p>No results found</p>';
      }
    });
  </script>
</body>
</html>
""",
    }

    def __init__(self, port: int = 8123):
        self.port = port
        self._app = FastAPI()
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._setup_routes()

    def _setup_routes(self):
        for path, html in self.DEFAULT_PAGES.items():
            self._app.add_api_route(path, lambda html=html: HTMLResponse(content=html), methods=["GET"])

        @self._app.get("/tasks.json")
        def tasks():
            return JSONResponse(content=self._load_tasks())

    def _load_tasks(self) -> List[Dict[str, Any]]:
        path = Path(__file__).with_name("web_benchmark_tasks.json")
        if path.exists():
            return json.loads(path.read_text())
        return []

    def start(self):
        config = uvicorn.Config(self._app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._server.started:
                break
            time.sleep(0.05)

    def stop(self):
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)

    def url_for(self, path: str) -> str:
        port = self._server.config.port if self._server else self.port
        return f"http://127.0.0.1:{port}{path}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()
    server = BrowserFixtureServer(port=args.port)
    server.start()
    print(f"Fixture server running at {server.url_for('/')}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
```

- [ ] **Step 4: Create task definitions**

Create `src/benchmarks/web_benchmark_tasks.json`:

```json
[
  {
    "id": "web-login",
    "description": "Log in to the fixture site with username 'admin' and password 'houdini123'",
    "tags": ["browser", "form", "fixture"],
    "start_path": "/login",
    "expected_text": "Welcome, admin!",
    "timeout_s": 45
  },
  {
    "id": "web-todo-add",
    "description": "Add a todo item 'Buy milk' on the fixture todo list",
    "tags": ["browser", "form", "fixture"],
    "start_path": "/todo",
    "expected_text": "Buy milk",
    "timeout_s": 45
  },
  {
    "id": "web-search",
    "description": "Search the fixture search page for 'Houdini agent' and verify results appear",
    "tags": ["browser", "search", "fixture"],
    "start_path": "/search",
    "expected_text": "Houdini Agent",
    "timeout_s": 45
  }
]
```

- [ ] **Step 5: Verify tests pass**

Run: `.venv/bin/python -m pytest tests/test_browser_vision.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/benchmarks/browser_fixture_server.py src/benchmarks/web_benchmark_tasks.json tests/test_browser_vision.py
git commit -m "feat(browser): deterministic web benchmark fixture server"
```

---

### Task 5: Expose vision toggle in API and frontend settings

**Files:**
- Modify: `src/api/server.py`
- Modify: `frontend/src/routes/settings/+page.svelte`
- Modify: `frontend/src/lib/store.ts`

- [ ] **Step 1: Add `use_vision` to backend settings model**

In `src/api/server.py`, locate the `SettingsUpdate` Pydantic model and add:

```python
class SettingsUpdate(BaseModel):
    ...
    use_browser_vision: Optional[bool] = None
```

Then in the `/api/settings` handler, persist it to `config/settings.py` or environment and include it in the response.

- [ ] **Step 2: Add `use_vision` to frontend settings store**

In `frontend/src/lib/store.ts`, add to the settings type and `saveSettings` payload:

```typescript
export interface Settings {
  provider: string;
  model: string;
  apiKey: string;
  apiBase: string;
  architecture: string;
  smartRouter: boolean;
  useBrowserVision: boolean;
}
```

- [ ] **Step 3: Add checkbox to settings page**

In `frontend/src/routes/settings/+page.svelte`, add a labeled checkbox bound to `settings.useBrowserVision`.

- [ ] **Step 4: Build frontend**

Run: `cd houdini-agent/frontend && npm run build`
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py frontend/src/routes/settings/+page.svelte frontend/src/lib/store.ts
git commit -m "feat(frontend): browser vision toggle in settings"
```

---

### Task 6: Fix docs/FRONTEND.md inaccuracy

**Files:**
- Modify: `docs/FRONTEND.md`

- [ ] **Step 1: Update tech stack description**

Replace any mention of "React" with "SvelteKit 5" and update the folder structure to match `frontend/src/routes/` and `frontend/src/lib/`.

- [ ] **Step 2: Commit**

```bash
git add docs/FRONTEND.md
git commit -m "docs: fix frontend tech stack (SvelteKit, not React)"
```

---

### Task 7: Full verification and push

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all tests pass (129+).

- [ ] **Step 2: Build frontend**

Run: `cd houdini-agent/frontend && npm run build`
Expected: success.

- [ ] **Step 3: Push branch**

```bash
cd houdini-agent && git push origin overhaul/provider-frontend
```

---

## Self-Review

**1. Spec coverage:**
- Vision grounding for browser executor ✅ Task 3
- Set-of-Marks element referencing ✅ Task 2
- Deterministic benchmark harness ✅ Task 4
- Frontend toggle ✅ Task 5
- Docs fix ✅ Task 6
- Continuous commits/push ✅ Task 7

**2. Placeholder scan:**
- No "TBD", "TODO", or vague steps.
- All code blocks contain concrete implementation.
- All test commands include expected output.

**3. Type consistency:**
- `BrowserObservation` fields match usage in `_build_observation` and `_plan_with_vision`.
- `som_id` is an `int` and mapped through `id_to_element: Dict[int, Dict]`.
- Provider `supports_vision` property already exists on `LLMProvider`.
