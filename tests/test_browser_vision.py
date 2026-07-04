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
