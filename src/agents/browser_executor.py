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

    def get_url(self) -> str:
        return self.page.url

    def get_title(self) -> str:
        return self.page.title()

    def screenshot(self) -> BrowserActionResult:
        try:
            png_bytes = self.page.screenshot(type="png")
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            return BrowserActionResult(success=True, data={"base64": b64}, screenshot=b64)
        except Exception as exc:
            return BrowserActionResult(success=False, message=f"Screenshot failed: {exc}")

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

    def execute_plan(self, plan: List[Dict[str, Any]]) -> List[BrowserActionResult]:
        """Execute a list of browser actions."""
        results = []
        for step in plan:
            action = step.get("action")
            if action == "goto":
                res = self.goto(step["url"])
            elif action == "click":
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
                res = self.screenshot()
            elif action == "get_text":
                res = self.get_text(step.get("selector"))
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

    def _plan(self, task: str, url: Optional[str] = None, page_text: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._get_client()
        context = f"Current URL: {url or 'unknown'}\nPage text:\n{page_text or 'N/A'}"[:2000]
        prompt = f"""You are controlling a headless Chromium browser via Playwright.
Task: {task}

{context}

Return a JSON array of actions. Available actions:
- {{"action": "goto", "url": "..."}}
- {{"action": "click", "selector": "..."}}  (Playwright selector)
- {{"action": "type", "selector": "...", "text": "...", "submit": true/false}}
- {{"action": "press", "key": "..."}}
- {{"action": "scroll", "direction": "down|up", "amount": 500}}
- {{"action": "wait", "selector": "..."}} or {{"action": "wait", "seconds": 2}}
- {{"action": "get_text", "selector": "..."}} (optional)

Respond with JSON only."""
        result = client.generate(prompt, temperature=0.2)
        text = result.text if hasattr(result, "text") else str(result)
        try:
            return client._extract_json(text)
        except Exception as exc:
            logger.warning(f"Browser plan JSON extraction failed: {exc}")
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
            for loop in range(max_loops):
                results = session.execute_plan(plan)
                all_results.extend(results)
                if all(r.success for r in results):
                    break
                # Replan from current state
                url = session.get_url()
                text_res = session.get_text()
                page_text = text_res.data.get("text", "") if text_res.success else ""
                plan = self._plan(task, url=url, page_text=page_text)
                if not plan:
                    break

            final_text = session.get_text()
            final_url = session.get_url()
            success = all(r.success for r in all_results) and bool(all_results)
            return {
                "success": success,
                "browser": True,
                "url": final_url,
                "page_text": final_text.data.get("text", "") if final_text.success else "",
                "actions": [{"message": r.message, "success": r.success} for r in all_results],
            }


def run_browser_task(task: str, client=None, headless: bool = True) -> Dict[str, Any]:
    """Convenience entry point."""
    runner = BrowserTaskRunner(client=client, headless=headless)
    return runner.run(task)
