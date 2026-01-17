
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class UIElement:
    role: str
    title: str
    value: str
    x: int
    y: int
    width: int
    height: int
    
    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

def analyze_and_execute_mock(action_description: str, elements: List[UIElement]):
    desc_lower = action_description.lower()
    
    # Extract search keywords matching vision_executor logic
    keywords = []
    import re
    quoted = re.findall(r'["\']([^"\']+)["\']', action_description)
    if quoted:
        keywords.extend([q.lower() for q in quoted])
    
    skip_words = {'click', 'on', 'the', 'a', 'an', 'button', 'link', 'element', 
                  'first', 'second', 'last', 'result', 'results', 'matching', 
                  'title', 'text', 'box', 'field', 'input', 'search', 'homepage',
                  'site', 'website', 'page'}
    words = [w.strip('.,!?') for w in desc_lower.split() 
             if w.strip('.,!?') and w.strip('.,!?') not in skip_words and len(w) > 2]
    keywords.extend(words)
    
    print(f"Keywords: {keywords}")
    
    screen_width, screen_height = 1920, 1080
    
    candidates = []
    for elem in elements:
        if elem.y < 25:
            continue
            
        title = (elem.title or '').lower()
        value = (elem.value or '').lower()
        role = elem.role.lower() if elem.role else ''
        text = f"{title} {value}"
        
        score = 0.0
        matched_keywords = []
        
        for kw in keywords:
            if kw in text:
                score += 0.4
                matched_keywords.append(kw)
        
        # Interactive role bonus
        interactive_roles = ['button', 'link', 'menuitem', 'checkbox', 'radiobutton', 
                            'textfield', 'searchfield', 'combobox']
        if any(r in role for r in interactive_roles):
            score += 0.3
        
        # Penalty for headers/footers 
        if elem.y < screen_height * 0.08:  # Top 8%
            score -= 0.2
        
        if score > 0:
            candidates.append((score, elem, matched_keywords))
    
    # Sort by score
    candidates.sort(key=lambda x: -x[0])
    
    if not candidates:
        print("No match initial")
        return

    # --- NEW LOGIC START ---
    
    # Check for explicit address bar intent
    explicit_nav_intent = any(w in desc_lower for w in ['address', 'url', 'link', 'bar', 'omnibox', 'browser', 'navigation'])
    
    refined_candidates = []
    for score, elem, matched in candidates:
        # Heuristic for browser address bar/omnibox
        is_top_region = elem.y < 110
        is_input_role = elem.role in ['textField', 'searchField', 'comboBox']
        val = (elem.value or '').strip()
        is_url_value = val.startswith('http') or val.startswith('www') or '://' in val or '.com' in val or '.org' in val or '.net' in val or '.io' in val
        
        is_likely_address_bar = is_top_region and is_input_role and is_url_value
        
        if is_likely_address_bar and not explicit_nav_intent:
            print(f"  📉 Applying penalty to '{elem.title or elem.value}'")
            score -= 0.5
        
        if score > 0:
            refined_candidates.append((score, elem, matched))
            
    candidates = sorted(refined_candidates, key=lambda x: -x[0])
    # --- NEW LOGIC END ---

    print("\nCandidates:")
    for score, elem, matched in candidates:
        print(f"Score: {score:.2f} | '{elem.title or elem.value}' | {elem.role} | matched: {matched}")

if __name__ == "__main__":
    address_bar = UIElement(
        role="textField",
        title="Address and Search Bar",
        value="https://uhdmovies.earth/",
        x=0, y=80, width=1000, height=30
    )
    
    some_link = UIElement(
        role="link",
        title="Movie Title",
        value="",
        x=200, y=400, width=100, height=20
    )
    
    elements = [address_bar, some_link]
    
    print("--- Simulation 1: 'search input field on uhdmovies.earth homepage' (Implicit) ---")
    analyze_and_execute_mock("search input field on uhdmovies.earth homepage", elements)
    
    print("\n--- Simulation 2: 'click address bar' (Explicit) ---")
    analyze_and_execute_mock("click address bar", elements)
