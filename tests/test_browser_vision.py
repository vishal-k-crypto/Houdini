"""Tests for browser vision grounding helpers."""

from src.agents.browser_observation import BrowserObservation


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
