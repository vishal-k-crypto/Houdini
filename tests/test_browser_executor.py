"""Tests for src/agents/browser_executor.py"""
import sys
import os
import base64
from unittest.mock import MagicMock, patch, call

import pytest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)

from src.agents.browser_executor import (
    BrowserSession,
    BrowserTaskRunner,
    BrowserActionResult,
    run_browser_task,
)


@pytest.fixture
def mock_page():
    return MagicMock()


@pytest.fixture
def mock_context(mock_page):
    ctx = MagicMock()
    ctx.new_page.return_value = mock_page
    return ctx


@pytest.fixture
def mock_browser(mock_context):
    browser = MagicMock()
    browser.new_context.return_value = mock_context
    return browser


@pytest.fixture
def mock_playwright(mock_browser):
    pw = MagicMock()
    pw.chromium.launch.return_value = mock_browser
    pw.stop = MagicMock()
    return pw


@pytest.fixture
def session(mock_playwright, mock_browser, mock_context, mock_page):
    with patch("src.agents.browser_executor.sync_playwright") as sync_pw:
        sync_pw.return_value.start.return_value = mock_playwright
        s = BrowserSession(headless=True)
        s.start()
        return s


class TestBrowserSession:
    """Unit tests for BrowserSession action methods."""

    def test_start_and_close(self, mock_playwright, mock_browser, mock_context, mock_page):
        with patch("src.agents.browser_executor.sync_playwright") as sync_pw:
            sync_pw.return_value.start.return_value = mock_playwright
            s = BrowserSession(headless=True)
            with s:
                assert s.page is mock_page
            mock_context.close.assert_called_once()
            mock_browser.close.assert_called_once()
            mock_playwright.stop.assert_called_once()

    def test_goto_success(self, session, mock_page):
        mock_page.goto.return_value = None
        result = session.goto("https://example.com")
        assert result.success is True
        assert "Navigated" in result.message
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded")

    def test_goto_failure(self, session, mock_page):
        mock_page.goto.side_effect = Exception("timeout")
        result = session.goto("https://example.com")
        assert result.success is False
        assert "Navigation failed" in result.message

    def test_click_success(self, session, mock_page):
        result = session.click("text=More information")
        assert result.success is True
        mock_page.click.assert_called_once_with("text=More information")

    def test_click_failure(self, session, mock_page):
        mock_page.click.side_effect = Exception("not found")
        result = session.click("text=Missing")
        assert result.success is False

    def test_type_text_with_submit(self, session, mock_page):
        result = session.type_text("#search", "Houdini", submit=True)
        assert result.success is True
        mock_page.fill.assert_called_once_with("#search", "Houdini")
        mock_page.press.assert_called_once_with("#search", "Enter")

    def test_press_key(self, session, mock_page):
        result = session.press_key("Escape")
        assert result.success is True
        mock_page.keyboard.press.assert_called_once_with("Escape")

    def test_scroll_down(self, session, mock_page):
        result = session.scroll(direction="down", amount=300)
        assert result.success is True
        mock_page.mouse.wheel.assert_called_once_with(0, -300)

    def test_wait_for_selector(self, session, mock_page):
        result = session.wait_for(selector="#results", seconds=2.0)
        assert result.success is True
        mock_page.wait_for_selector.assert_called_once_with("#results", timeout=2000)

    def test_wait_seconds(self, session, mock_page):
        result = session.wait_for(seconds=0.05)
        assert result.success is True
        mock_page.wait_for_selector.assert_not_called()

    def test_get_text_body(self, session, mock_page):
        mock_page.inner_text.return_value = "Hello world"
        result = session.get_text()
        assert result.success is True
        assert result.data["text"] == "Hello world"

    def test_get_text_selector(self, session, mock_page):
        element = MagicMock()
        element.inner_text.return_value = "Selected text"
        mock_page.query_selector.return_value = element
        result = session.get_text("#heading")
        assert result.success is True
        assert result.data["text"] == "Selected text"

    def test_screenshot(self, session, mock_page):
        mock_page.screenshot.return_value = b"pngbytes"
        result = session.screenshot()
        assert result.success is True
        assert result.data["base64"] == base64.b64encode(b"pngbytes").decode("utf-8")
        assert result.screenshot == result.data["base64"]

    def test_execute_plan_stops_on_failure(self, session, mock_page):
        mock_page.goto.side_effect = Exception("bad url")
        plan = [
            {"action": "goto", "url": "https://example.com"},
            {"action": "click", "selector": "text=More"},
        ]
        results = session.execute_plan(plan)
        assert len(results) == 1
        assert results[0].success is False
        mock_page.click.assert_not_called()

    def test_execute_plan_unknown_action(self, session, mock_page):
        results = session.execute_plan([{"action": "dance"}])
        assert len(results) == 1
        assert results[0].success is False
        assert "Unknown action" in results[0].message


class TestBrowserTaskRunner:
    """Unit tests for BrowserTaskRunner task detection and execution."""

    @pytest.mark.parametrize(
        "task,expected",
        [
            ("Search Google for Houdini", True),
            ("Open the website example.com", True),
            ("Fill the login form on the page", True),
            ("Click on the submit button", True),
            ("Go to https://example.com", True),
            ("Open Safari", False),
            ("Type hello in TextEdit", False),
            ("Copy and paste a file", False),
        ],
    )
    def test_is_browser_task(self, task, expected):
        runner = BrowserTaskRunner()
        assert runner._is_browser_task(task) is expected

    def test_run_skips_non_browser_task(self):
        runner = BrowserTaskRunner()
        result = runner.run("Open TextEdit")
        assert result["success"] is False
        assert result["browser"] is False

    def test_run_browser_task_success(self):
        fake_result = {
            "success": True,
            "browser": True,
            "url": "https://example.com",
            "page_text": "Example Domain",
            "actions": [{"message": "Navigated", "success": True}],
        }
        with patch("src.agents.browser_executor.BrowserSession") as MockSession:
            instance = MockSession.return_value.__enter__.return_value
            instance.execute_plan.return_value = [
                BrowserActionResult(success=True, message="Navigated")
            ]
            instance.get_text.return_value = BrowserActionResult(
                success=True, data={"text": "Example Domain"}
            )
            instance.get_url.return_value = "https://example.com"

            runner = BrowserTaskRunner()
            with patch.object(runner, "_plan", return_value=[{"action": "goto", "url": "https://example.com"}]):
                result = runner.run("Open https://example.com")

        assert result["success"] is True
        assert result["browser"] is True
        assert result["url"] == "https://example.com"

    def test_run_browser_task_no_plan(self):
        with patch("src.agents.browser_executor.BrowserSession") as MockSession:
            runner = BrowserTaskRunner()
            with patch.object(runner, "_plan", return_value=[]):
                result = runner.run("Open https://example.com")
        assert result["success"] is False
        assert "Could not build browser plan" in result["error"]


class TestRunBrowserTaskConvenience:
    def test_convenience_entry_point(self):
        with patch("src.agents.browser_executor.BrowserTaskRunner") as MockRunner:
            MockRunner.return_value.run.return_value = {"success": True, "browser": True}
            result = run_browser_task("Search Google for Houdini")
        assert result["success"] is True
        MockRunner.assert_called_once_with(client=None, headless=True)
