"""Test fast coordinate predictor with WhatsApp"""

from src.utils.coordinate_predictor import get_predictor

print("=== Fast Coordinate Prediction Test ===\n")

predictor = get_predictor()

# Test 1: Search bar
print("Test 1: Finding WhatsApp search bar...")
result = predictor.predict_coordinates(
    element_description="search field or search input box",
    app_name="WhatsApp",
    window_title="WhatsApp",
    context="Looking for the search bar to search for contacts"
)

print(f"Found: {result['found']}")
print(f"Coordinates: ({result['x']}, {result['y']})")
print(f"Confidence: {result['confidence']:.0%}")
print(f"Match Probability: {result['match_probability']:.0%}")
print(f"Element: {result['element']}")
print(f"Reasoning: {result['reasoning']}")
print()

# Test 2: Contact named kushal
print("Test 2: Finding contact 'kushal'...")
result2 = predictor.predict_coordinates(
    element_description="contact or chat named kushal (might match Kushal RU or similar)",
    app_name="WhatsApp",
    window_title="WhatsApp",
    context="Need to click on the contact kushal to open chat"
)

print(f"Found: {result2['found']}")
print(f"Coordinates: ({result2['x']}, {result2['y']})")
print(f"Confidence: {result2['confidence']:.0%}")
print(f"Match Probability: {result2['match_probability']:.0%}")
print(f"Element: {result2['element']}")
print(f"Reasoning: {result2['reasoning']}")
print()

print("✅ Fast prediction test complete!")
