"""Tests for browser vision grounding helpers."""

import base64
from typing import Tuple
from unittest.mock import MagicMock

from src.agents.browser_observation import BrowserObservation


def _make_png_b64(width: int = 100, height: int = 100, color: Tuple[int, int, int] = (255, 255, 255)) -> str:
    from PIL import Image
    import io, base64
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_browser_observation_builds():
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


def test_browser_observation_defaults():
    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64="iVBORw0KGgo=",
        accessibility_tree={"role": "WebArea", "name": "Example"},
    )
    assert obs.interactive_elements == []
    assert obs.clean_text == ""
    assert obs.action_history == []


def test_browser_observation_to_text_context():
    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64="iVBORw0KGgo=",
        accessibility_tree={"role": "WebArea", "name": "Example"},
        clean_text="Example Domain",
    )
    context = obs.to_text_context()
    assert obs.url in context
    assert obs.title in context
    assert obs.clean_text in context

    long_text = "a" * 5000
    obs_long = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64="iVBORw0KGgo=",
        accessibility_tree={"role": "WebArea", "name": "Example"},
        clean_text=long_text,
    )
    context_long = obs_long.to_text_context(max_chars=100)
    assert len(context_long) < len(long_text)
    assert long_text[:100] in context_long


def test_browser_observation_invalid_base64():
    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64="not-valid-base64!!!",
        accessibility_tree={"role": "WebArea", "name": "Example"},
    )
    try:
        _ = obs.screenshot_bytes
        assert False, "Expected ValueError for invalid base64"
    except ValueError as exc:
        assert str(exc) == "Invalid base64 screenshot data"


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


def test_som_renderer_empty_elements():
    from src.agents.browser_som import SetOfMarksRenderer
    from PIL import Image

    img = Image.new("RGB", (100, 100), color="white")
    renderer = SetOfMarksRenderer()
    result = renderer.render(img, [])

    assert result.marks == []
    assert isinstance(result.base64_png, str)
    assert len(result.base64_png) > 0


def test_som_renderer_skips_invalid_bbox():
    from src.agents.browser_som import SetOfMarksRenderer
    from PIL import Image

    img = Image.new("RGB", (200, 200), color="white")
    elements = [
        {"id": "no-bbox", "tag": "button", "text": "No bbox"},
        {"id": "zero-width", "bbox": {"x": 10, "y": 10, "width": 0, "height": 20}, "tag": "button"},
        {"id": "negative-height", "bbox": {"x": 10, "y": 10, "width": 30, "height": -5}, "tag": "button"},
        {"id": "valid", "bbox": {"x": 50, "y": 50, "width": 40, "height": 30}, "tag": "button", "text": "Valid"},
    ]
    renderer = SetOfMarksRenderer()
    result = renderer.render(img, elements)

    assert len(result.marks) == 1
    assert result.marks[0]["text"] == "Valid"
    assert result.id_to_element[result.marks[0]["som_id"]]["text"] == "Valid"


def test_som_renderer_base64_png():
    from src.agents.browser_som import SetOfMarksRenderer
    from PIL import Image

    img = Image.new("RGB", (100, 100), color="white")
    elements = [
        {"id": "btn-1", "bbox": {"x": 10, "y": 10, "width": 40, "height": 20}, "tag": "button", "text": "OK"},
    ]
    renderer = SetOfMarksRenderer()
    result = renderer.render(img, elements)

    assert isinstance(result.base64_png, str)
    assert len(result.base64_png) > 0
    decoded = base64.b64decode(result.base64_png)
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")


def test_vision_plan_uses_som_when_provider_supports_vision():
    from src.agents.browser_executor import BrowserTaskRunner
    from src.agents.browser_observation import BrowserObservation

    mock_client = MagicMock()
    mock_client.supports_vision = True
    mock_client.generate.return_value.text = '[{"action": "click", "som_id": 1}]'
    mock_client._extract_json.return_value = [{"action": "click", "som_id": 1}]

    runner = BrowserTaskRunner(client=mock_client, headless=True)

    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64=_make_png_b64(),
        accessibility_tree={},
        interactive_elements=[{"id": "el-btn", "tag": "button", "text": "OK", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}],
        clean_text="Example Domain",
    )

    plan = runner._plan("Click the OK button", observation=obs)
    assert plan == [{"action": "click", "som_id": 1, "selector": "text=OK"}]
    assert mock_client.generate.call_args.kwargs.get("images")


def test_resolve_som_ids_unknown_id_skipped():
    from src.agents.browser_executor import BrowserTaskRunner

    runner = BrowserTaskRunner(client=None, headless=True)
    plan = [{"action": "click", "som_id": 99}]
    id_to_element = {1: {"id": "btn", "tag": "button", "text": "OK"}}

    resolved = runner._resolve_som_ids(plan, id_to_element)
    assert resolved == []


def test_resolve_som_ids_missing_tag():
    from src.agents.browser_executor import BrowserTaskRunner

    runner = BrowserTaskRunner(client=None, headless=True)
    plan = [{"action": "click", "som_id": 1}]
    id_to_element = {1: {"id": "el-1"}}

    resolved = runner._resolve_som_ids(plan, id_to_element)
    assert resolved == []


def test_vision_plan_fallback_on_invalid_screenshot():
    from src.agents.browser_executor import BrowserTaskRunner

    mock_client = MagicMock()
    mock_client.supports_vision = True
    mock_client.generate.return_value.text = '[{"action": "goto", "url": "https://example.com"}]'
    mock_client._extract_json.return_value = [{"action": "goto", "url": "https://example.com"}]

    runner = BrowserTaskRunner(client=mock_client, headless=True)
    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64="not-valid-base64",
        accessibility_tree={},
        interactive_elements=[],
        clean_text="Example Domain",
    )

    plan = runner._plan("Go to example", observation=obs)
    assert plan == [{"action": "goto", "url": "https://example.com"}]


def test_vision_plan_text_only_when_provider_lacks_vision():
    from src.agents.browser_executor import BrowserTaskRunner

    mock_client = MagicMock()
    mock_client.supports_vision = False
    mock_client.generate.return_value.text = '[{"action": "goto", "url": "https://example.com"}]'
    mock_client._extract_json.return_value = [{"action": "goto", "url": "https://example.com"}]

    runner = BrowserTaskRunner(client=mock_client, headless=True)
    obs = BrowserObservation(
        url="https://example.com",
        title="Example",
        screenshot_b64=_make_png_b64(),
        accessibility_tree={},
        interactive_elements=[],
        clean_text="Example Domain",
    )

    plan = runner._plan("Go to example", observation=obs)
    assert plan == [{"action": "goto", "url": "https://example.com"}]
    assert "images" not in mock_client.generate.call_args.kwargs
