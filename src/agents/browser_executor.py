"""Headless browser executor for web-only tasks.

This executor lets Houdini compete on browser-agent benchmarks and handle
web-first tasks (search, form fill, navigation, data extraction) without
depending on native desktop automation. It uses Playwright and can run
completely headless or with a visible Chromium window.

Usage:
    from src.agents.browser_executor import BrowserSession

    with BrowserSession(headless=True) as session:
        session.goto("https://example.com")
        session.click("text=More information")
        text = session.get_text()
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils.logging import logger

try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Browser = BrowserContext = Any  # type: ignore


@dataclass
class BrowserActionResult:
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    screenshot: Optional[str] = None  # base64 PNG


class BrowserSession:
    """A managed Playwright browser session."""

    def __init__(
        self,
        headless: bool = True,
        browser_type: str = "chromium",
        viewport: Optional[Dict[str, int]] = None,
        user_agent: Optional[str] = None,
        slow_mo: Optional[float] = None,
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

        self.headless = headless
        self.browser_type = browser_type
        self.viewport = viewport or {"width": 1280, "height": 800}
        self.user_agent = user_agent
        self.slow_mo = slow_mo

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        logger.info(f"🌐 Starting browser session ({self.browser_type}, headless={self.headless})")
        self._playwright = sync_playwright().start()
        browser_launcher = getattr(self._playwright, self.browser_type)
        args = {"headless": self.headless}
        if self.slow_mo is not None:
            args["slow_mo"] = int(self.slow_mo * 1000)
        self._browser = browser_launcher.launch(**args)

        context_args: Dict[str, Any] = {"viewport": self.viewport}
        if self.user_agent:
            context_args["user_agent"] = self.user_agent
        self._context = self._browser.new_context(**context_args)
        self._page = self._context.new_page()
        self._page.set_default_timeout(30000)

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as exc:
            logger.warning(f"Browser cleanup error: {exc}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser session not started")
        return self._page

    # ── Core actions ───────────────────────────────────────────────────

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> BrowserActionResult:
        try:
            self.page.goto(url, wait_until=wait_until)
            return BrowserActionResult(success=True, message=f"Navigated to {url}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Navigation failed: {exc}")

    def click(self, selector: str) -> BrowserActionResult:
        try:
            self.page.click(selector)
            return BrowserActionResult(success=True, message=f"Clicked {selector}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Click failed: {exc}")

    def type_text(self, selector: str, text: str, submit: bool = False) -> BrowserActionResult:
        try:
            self.page.fill(selector, text)
            if submit:
                self.page.press(selector, "Enter")
            return BrowserActionResult(success=True, message=f"Typed into {selector}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Type failed: {exc}")

    def press_key(self, key: str) -> BrowserActionResult:
        try:
            self.page.keyboard.press(key)
            return BrowserActionResult(success=True, message=f"Pressed {key}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Key press failed: {exc}")

    def scroll(self, direction: str = "down", amount: int = 500) -> BrowserActionResult:
        try:
            delta = -amount if direction == "down" else amount
            self.page.mouse.wheel(0, delta)
            return BrowserActionResult(success=True, message=f"Scrolled {direction}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Scroll failed: {exc}")

    def wait_for(self, selector: Optional[str] = None, seconds: Optional[float] = None) -> BrowserActionResult:
        try:
            if selector:
                self.page.wait_for_selector(selector, timeout=int(seconds * 1000) if seconds else 30000)
            elif seconds:
                time.sleep(seconds)
            return BrowserActionResult(success=True, message="Wait complete")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Wait failed: {exc}")

    def get_text(self, selector: Optional[str] = None) -> BrowserActionResult:
        try:
            if selector:
                element = self.page.query_selector(selector)
                text = element.inner_text() if element else ""
            else:
                text = self.page.inner_text("body")
            return BrowserActionResult(success=True, data={"text": text})
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Get text failed: {exc}")

    def get_clean_text(self, max_chars: int = 4000) -> BrowserActionResult:
        """Return a cleaned, compact text representation of the page."""
        try:
            text = self.page.inner_text("body")
            # Collapse whitespace and truncate
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            cleaned = "\n".join(lines)
            if len(cleaned) > max_chars:
                cleaned = cleaned[:max_chars] + "\n...[truncated]"
            return BrowserActionResult(success=True, data={"text": cleaned})
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Get clean text failed: {exc}")

    def get_accessibility_snapshot(self) -> BrowserActionResult:
        """Return an accessibility tree snapshot for structured page understanding."""
        try:
            snapshot = self.page.accessibility.snapshot()
            return BrowserActionResult(success=True, data={"snapshot": snapshot})
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Accessibility snapshot failed: {exc}")

    def get_interactive_elements(self) -> BrowserActionResult:
        """Return a list of interactive elements with bounding boxes."""
        try:
            elements = self.page.evaluate("""
                () => {
                    const tags = [
                        'a', 'button', 'input', 'select', 'textarea',
                        '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]'
                    ];
                    const out = [];
                    document.querySelectorAll(tags.join(',')).forEach((el, idx) => {
                        const style = getComputedStyle(el);
                        if (style.visibility === 'hidden' || style.display === 'none') {
                            return;
                        }
                        if (style.pointerEvents === 'none' || el.disabled) {
                            return;
                        }
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) {
                            return;
                        }
                        if (rect.bottom <= 0 || rect.right <= 0 || rect.top >= window.innerHeight || rect.left >= window.innerWidth) {
                            return;
                        }
                        out.push({
                            id: el.id || `el-${idx}`,
                            tag: el.tagName.toLowerCase(),
                            text: (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').slice(0, 100),
                            type: el.type || null,
                            bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
                        });
                    });
                    return out;
                }
            """)
            return BrowserActionResult(success=True, data={"elements": elements})
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Element extraction failed: {exc}")

    def get_url(self) -> str:
        return self.page.url

    def get_title(self) -> str:
        return self.page.title()

    def screenshot(self, full_page: bool = False) -> BrowserActionResult:
        try:
            png_bytes = self.page.screenshot(type="png", full_page=full_page)
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            return BrowserActionResult(success=True, data={"base64": b64}, screenshot=b64)
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Screenshot failed: {exc}")

    def hover(self, selector: str) -> BrowserActionResult:
        try:
            self.page.hover(selector)
            return BrowserActionResult(success=True, message=f"Hovered {selector}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Hover failed: {exc}")

    def select_option(self, selector: str, value: Optional[str] = None, label: Optional[str] = None) -> BrowserActionResult:
        try:
            if label:
                self.page.select_option(selector, label=label)
            else:
                self.page.select_option(selector, value=value)
            return BrowserActionResult(success=True, message=f"Selected option on {selector}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Select failed: {exc}")

    def upload_file(self, selector: str, file_path: str) -> BrowserActionResult:
        try:
            self.page.set_input_files(selector, file_path)
            return BrowserActionResult(success=True, message=f"Uploaded {file_path} to {selector}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Upload failed: {exc}")

    def drag(self, from_selector: str, to_selector: str) -> BrowserActionResult:
        try:
            self.page.drag_and_drop(from_selector, to_selector)
            return BrowserActionResult(success=True, message=f"Dragged {from_selector} to {to_selector}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Drag failed: {exc}")

    def switch_frame(self, name_or_index: Any) -> BrowserActionResult:
        try:
            if isinstance(name_or_index, int):
                frames = self.page.frames
                if name_or_index < len(frames):
                    self._page = frames[name_or_index].page if hasattr(frames[name_or_index], "page") else frames[name_or_index]
                else:
                    raise IndexError(f"Frame index {name_or_index} out of range")
            else:
                self.page.frame(name=name_or_index)
            return BrowserActionResult(success=True, message=f"Switched to frame {name_or_index}")
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Frame switch failed: {exc}")

    def retry_click(self, selector: str, fallback_selectors: Optional[List[str]] = None, retries: int = 2) -> BrowserActionResult:
        """Click with retries and optional fallback selectors."""
        selectors = [selector] + (fallback_selectors or [])
        last_error = ""
        for attempt in range(retries):
            for sel in selectors:
                try:
                    self.page.click(sel, timeout=5000)
                    return BrowserActionResult(success=True, message=f"Clicked {sel}")
                except Exception as exc:
                    last_error = str(exc)
            time.sleep(0.5)
        return BrowserActionResult(success=False, message=f"Click failed after retries: {last_error}")

    # ── High-level helpers ─────────────────────────────────────────────

    def search(self, url: str, query: str, input_selector: str, submit: bool = True) -> BrowserActionResult:
        nav = self.goto(url)
        if not nav.success:
            return nav
        type_res = self.type_text(input_selector, query, submit=submit)
        if not type_res.success:
            return type_res
        self.wait_for(seconds=2)
        return BrowserActionResult(success=True, message=f"Searched '{query}' on {url}")

    def execute_plan(self, plan: List[Dict[str, Any]], use_retries: bool = True) -> List[BrowserActionResult]:
        """Execute a list of browser actions."""
        results = []
        for step in plan:
            action = step.get("action")
            if action == "goto":
                res = self.goto(step["url"])
            elif action == "click":
                if use_retries:
                    res = self.retry_click(step["selector"], step.get("fallback_selectors"))
                else:
                    res = self.click(step["selector"])
            elif action == "type":
                res = self.type_text(step["selector"], step["text"], step.get("submit", False))
            elif action == "press":
                res = self.press_key(step["key"])
            elif action == "scroll":
                res = self.scroll(step.get("direction", "down"), step.get("amount", 500))
            elif action == "wait":
                res = self.wait_for(selector=step.get("selector"), seconds=step.get("seconds"))
            elif action == "screenshot":
                res = self.screenshot(full_page=step.get("full_page", False))
            elif action == "get_text":
                res = self.get_text(step.get("selector"))
            elif action == "get_clean_text":
                res = self.get_clean_text(max_chars=step.get("max_chars", 4000))
            elif action == "hover":
                res = self.hover(step["selector"])
            elif action == "select":
                res = self.select_option(step["selector"], value=step.get("value"), label=step.get("label"))
            elif action == "upload":
                res = self.upload_file(step["selector"], step["file_path"])
            elif action == "drag":
                res = self.drag(step["from"], step["to"])
            elif action == "switch_frame":
                res = self.switch_frame(step["frame"])
            elif action == "get_interactive_elements":
                res = self.get_interactive_elements()
            else:
                res = BrowserActionResult(success=False, message=f"Unknown action: {action}")
            results.append(res)
            if not res.success:
                break
        return results


class BrowserTaskRunner:
    """Run a natural-language task in a browser by planning and executing."""

    def __init__(self, client=None, headless: bool = True):
        self.client = client
        self.headless = headless

    def _get_client(self):
        if self.client is not None:
            return self.client
        from ..providers.router import get_provider
        return get_provider("worker")

    def _is_browser_task(self, task: str) -> bool:
        keywords = [
            "browser", "website", "web", "search google", "search bing",
            "open url", "open http", "open https", "open the url",
            "click on", "fill form", "fill the form", "fill in", "form",
            "login to", "login", "sign in", "signin",
            "go to", "navigate to", "http", "https", "url",
        ]
        task_l = task.lower()
        return any(kw in task_l for kw in keywords)

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

        try:
            img = Image.open(io.BytesIO(observation.screenshot_bytes))
        except Exception as exc:
            logger.warning(f"Browser vision screenshot unreadable, falling back to text plan: {exc}")
            return self._plan_text_only(client, task, observation, action_history, skills_text)
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

    def _element_to_selector(self, element: Dict[str, Any]) -> Optional[str]:
        """Build a stable Playwright selector from an element descriptor."""
        element_id = element.get("id")
        if element_id and not str(element_id).startswith("el-"):
            return f"#{element_id}"
        if element.get("text"):
            return f"text={element['text']}"
        tag = element.get("tag")
        element_type = element.get("type")
        if tag and element_type:
            return f"{tag}[type='{element_type}']"
        if tag:
            return tag
        return None

    def _resolve_som_ids(
        self,
        plan: List[Dict[str, Any]],
        id_to_element: Dict[int, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert som_id references into stable Playwright selectors."""
        resolved = []
        for step in plan:
            step = dict(step)
            som_id = step.get("som_id")
            if som_id is not None:
                if som_id not in id_to_element:
                    logger.warning(f"Unknown som_id {som_id}; skipping step {step}")
                    continue
                element = id_to_element[som_id]
                selector = self._element_to_selector(element)
                if selector is None:
                    logger.warning(f"Could not build selector for som_id {som_id}; skipping step {step}")
                    continue
                step["selector"] = selector
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

    @staticmethod
    def _format_accessibility_snapshot(snapshot: Dict, max_nodes: int = 50) -> str:
        """Convert an accessibility snapshot into a compact text summary."""
        lines = []
        def _walk(node, depth=0):
            if len(lines) >= max_nodes:
                return
            role = node.get("role", "")
            name = node.get("name", "")
            if role and name:
                lines.append(f"{'  '*depth}[{role}] {name}")
            for child in node.get("children", []):
                _walk(child, depth + 1)
        _walk(snapshot)
        return "\n".join(lines)

    def _verify_completion(
        self,
        task: str,
        url: str,
        page_text: str,
        action_history: List[str],
    ) -> Dict[str, Any]:
        """Ask the LLM whether the browser task is complete and why."""
        client = self._get_client()
        history_text = "\n".join(f"- {a}" for a in action_history[-15:]) or "None"
        prompt = f"""You are verifying whether a web automation task has been completed successfully.

Task: {task}
Final URL: {url}
Actions taken:
{history_text}

Page content:
{page_text[:2000]}

Respond with STRICT JSON only:
{{
  "complete": true/false,
  "reason": "one sentence explaining why",
  "missing": "what still needs to be done, if anything"
}}"""
        try:
            result = client.generate(prompt, temperature=0.1)
            text = result.text if hasattr(result, "text") else str(result)
            parsed = client._extract_json(text)
            return {
                "complete": bool(parsed.get("complete", False)),
                "reason": str(parsed.get("reason", "")),
                "missing": str(parsed.get("missing", "")),
            }
        except Exception as exc:
            logger.warning(f"Browser completion verification failed: {exc}")
            return {"complete": False, "reason": f"Verification failed: {exc}", "missing": ""}

    def _reflect(
        self,
        task: str,
        url: str,
        page_text: str,
        action_history: List[str],
        missing: str,
    ) -> List[Dict[str, Any]]:
        """Generate a repair plan when verification shows the task is incomplete."""
        client = self._get_client()
        snapshot_text = ""
        skills_text = ""
        try:
            from ..skills.registry import skill_registry
            skills_text = skill_registry.prompt_for_task(task, top_k=2, min_score=1.0)
        except Exception:
            pass
        history_text = "\n".join(f"- {a}" for a in action_history[-15:]) or "None"
        prompt = f"""You are controlling a headless Chromium browser. The previous attempt did not fully complete the task.

{skills_text}

Task: {task}
Current URL: {url}
Actions already taken:
{history_text}

What is still missing: {missing}

Page content:
{page_text[:2000]}

Return a JSON array of additional actions to finish the task. Use the same action schema as before.

Respond with JSON only."""
        try:
            result = client.generate(prompt, temperature=0.2)
            text = result.text if hasattr(result, "text") else str(result)
            return client._extract_json(text)
        except Exception as exc:
            logger.warning(f"Browser reflection plan generation failed: {exc}")
            return []

    def run(self, task: str) -> Dict[str, Any]:
        if not self._is_browser_task(task):
            return {"success": False, "error": "Not a browser task", "browser": False}

        with BrowserSession(headless=self.headless) as session:
            observation = self._build_observation(session)
            plan = self._plan(task, observation=observation)
            if not plan:
                return {"success": False, "error": "Could not build browser plan"}

            # Execute up to 3 replanning loops
            max_loops = 3
            all_results: List[BrowserActionResult] = []
            action_history: List[str] = []
            for loop in range(max_loops):
                results = session.execute_plan(plan)
                all_results.extend(results)
                action_history.extend(r.message for r in results if r.success)
                if all(r.success for r in results):
                    break
                # Replan from current state with richer context
                observation = self._build_observation(session)
                plan = self._plan(task, observation=observation, action_history=action_history)
                if not plan:
                    break

            final_text = session.get_clean_text(max_chars=4000)
            final_url = session.get_url()
            page_text = final_text.data.get("text", "") if final_text.success else ""
            success = all(r.success for r in all_results) and bool(all_results)

            # Verification + reflection
            if success:
                verification = self._verify_completion(task, final_url, page_text, action_history)
                if not verification.get("complete"):
                    for reflect_loop in range(2):
                        repair_plan = self._reflect(
                            task, final_url, page_text, action_history, verification.get("missing", "")
                        )
                        if not repair_plan:
                            break
                        repair_results = session.execute_plan(repair_plan)
                        all_results.extend(repair_results)
                        action_history.extend(r.message for r in repair_results if r.success)
                        final_url = session.get_url()
                        final_text = session.get_clean_text(max_chars=4000)
                        page_text = final_text.data.get("text", "") if final_text.success else ""
                        if all(r.success for r in repair_results):
                            verification = self._verify_completion(task, final_url, page_text, action_history)
                            if verification.get("complete"):
                                break
                        else:
                            break
                success = verification.get("complete", success)

            return {
                "success": success,
                "browser": True,
                "url": final_url,
                "page_text": page_text,
                "actions": [{"message": r.message, "success": r.success} for r in all_results],
                "verified": success,
            }


def run_browser_task(task: str, client=None, headless: bool = True) -> Dict[str, Any]:
    """Convenience entry point."""
    runner = BrowserTaskRunner(client=client, headless=headless)
    return runner.run(task)
