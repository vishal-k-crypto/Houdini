
import sys
import os
from dataclasses import dataclass

# Mock AccessibilityElement
@dataclass
class AccessibilityElement:
    role: str
    title: str
    value: str
    x: int
    y: int
    width: int
    height: int
    
    @property
    def center(self):
        return (self.x + self.width//2, self.y + self.height//2)

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.probability_model import ElementAffordanceScorer

def test_affordance_logic():
    print("🧪 Testing Element Affordance Logic...")
    scorer = ElementAffordanceScorer()
    
    # Scene: User wants to "Download 1080p"
    intent = {
        "action": "click",
        "keywords": ["1080p"],
        "target_type": "link"
    }
    screen_height = 1000
    
    # Candidate 1: The Trap - A generic header at the top
    header_1080p = AccessibilityElement(
        role="staticText",
        title="1080p",
        value="",
        x=200, y=50, # Top of screen
        width=100, height=20
    )
    
    # Candidate 2: The Target - A button in the content area
    button_1080p = AccessibilityElement(
        role="button",
        title="Download 1080p",
        value="",
        x=200, y=400, # Middle of screen
        width=100, height=40
    )
    
    score1 = scorer.score_element(header_1080p, intent, screen_height)
    score2 = scorer.score_element(button_1080p, intent, screen_height)
    
    print(f"\n1. Header '1080p' (Top):")
    print(f"   Score: {score1.probability:.2f}")
    print(f"   Reason: {score1.reason}")
    print(f"   Is Target: {score1.is_target}")
    
    print(f"\n2. Button 'Download 1080p' (Middle):")
    print(f"   Score: {score2.probability:.2f}")
    print(f"   Reason: {score2.reason}")
    print(f"   Is Target: {score2.is_target}")
    
    # Verification
    if score1.probability < 0.5 and score2.probability > 0.7:
        print("\n✅ SUCCESS: Logic correctly prioritized Button over Header.")
        if "top_header_penalty" in score1.reason:
            print("   - Header penalty applied correctly.")
        if "interactive_role" in score2.reason:
            print("   - Interactive role bonus applied correctly.")
    else:
        print("\n❌ FAILED: Logic did not prioritize correctly.")
        exit(1)

if __name__ == "__main__":
    test_affordance_logic()
