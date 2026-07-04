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
        url: Optional[str] = None,
        page_text: Optional[str] = None,
        accessibility_snapshot: Optional[Dict] = None,
        action_history: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        client = self._get_client()
        snapshot_text = ""
        if accessibility_snapshot:
            snapshot_text = self._format_accessibility_snapshot(accessibility_snapshot, max_nodes=50)
        context = (
            f"Current URL: {url or 'unknown'}\n"
            f"Page text:\n{page_text or 'N/A'}\n"
            f"Accessibility tree:\n{snapshot_text or 'N/A'}"
        )
        if action_history:
            context += f"\n\nActions already taken:\n" + "\n".join(f"- {a}" for a in action_history[-10:])
        context = context[:4000]

        # Inject relevant skills as system guidance
        skills_text = ""
        try:
            from ..skills.registry import skill_registry
            skills_text = skill_registry.prompt_for_task(task, top_k=2, min_score=1.0)
        except Exception:
            pass

        prompt = f"""You are controlling a headless Chromium browser via Playwright to complete a real-world web task.

{skills_text}

Task: {task}

{context}

Return a JSON array of actions. Prefer stable selectors: exact text matches like `text=Submit`, semantic roles like `[placeholder='Search']`, or IDs. Avoid brittle XPath.

Available actions:
- {{"action": "goto", "url": "..."}}
- {{"action": "click", "selector": "...", "fallback_selectors": ["..."]}}
- {{"action": "type", "selector": "...", "text": "...", "submit": true/false}}
- {{"action": "press", "key": "..."}}
- {{"action": "scroll", "direction": "down|up", "amount": 500}}
- {{"action": "wait", "selector": "..."}} or {{"action": "wait", "seconds": 2}}
- {{"action": "hover", "selector": "..."}}
- {{"action": "select", "selector": "...", "value": "..."}} or {{"label": "..."}}
- {{"action": "get_text", "selector": "..."}}
- {{"action": "get_clean_text"}}
- {{"action": "screenshot"}}

Guidelines:
1. Start by navigating to the right page if no URL is loaded.
2. Click before typing into a field unless it is already focused.
3. Wait after navigation, form submission, or AJAX-heavy interactions.
4. If a search box exists, use `type` with `submit: true` rather than pressing Enter separately.
5. If the task asks for information, end with `get_text` or `get_clean_text`.
6. Do not assume success; verify the result when possible.

Respond with JSON only."""
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
            # Initial plan
            plan = self._plan(task)
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
                url = session.get_url()
                text_res = session.get_clean_text(max_chars=3000)
                page_text = text_res.data.get("text", "") if text_res.success else ""
                snapshot_res = session.get_accessibility_snapshot()
                snapshot = snapshot_res.data.get("snapshot") if snapshot_res.success else None
                plan = self._plan(task, url=url, page_text=page_text, accessibility_snapshot=snapshot, action_history=action_history)
                if not plan:
                    break

            final_text = session.get_clean_text(max_chars=4000)
            final_url = session.get_url()
            page_text = final_text.data.get("text", "") if final_text.success else ""
            success = all(r.success for r in all_results) and bool(all_results)

            # Verification + reflection: even if actions succeeded, ask the LLM
            # whether the task goal is actually satisfied.
            if success:
                verification = self._verify_completion(task, final_url, page_text, action_history)
                if not verification.get("complete"):
                    # Try up to 2 reflection loops to finish missing steps
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
