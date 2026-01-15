"""
Robust Task Verification and Continuous Improvement System
Keeps trying different approaches until task is actually complete.
"""

import time
from typing import Dict, List, Optional
from ..utils.logging import logger
from ..utils.coordinate_predictor import get_predictor


class TaskVerifier:
    """
    Verifies task completion using multiple methods and suggests improvements.
    """
    
    def __init__(self, llm_client=None):
        """Initialize task verifier."""
        self.llm_client = llm_client
        self.verification_history = []
        self.max_retries = 5
        self.predictor = get_predictor()
    
    def verify_task_complete(
        self,
        task_description: str,
        actions_taken: List[Dict],
        current_state: Dict
    ) -> Dict:
        """
        Verify if task is complete using multiple verification methods.
        
        Returns:
            {
                "complete": bool,
                "confidence": float (0-1),
                "reason": str,
                "evidence": List[str],
                "next_steps": List[Dict] if not complete
            }
        """
        verifications = []
        
        # Method 1: Screen state analysis
        screen_verification = self._verify_by_screen_state(
            task_description,
            current_state
        )
        verifications.append(screen_verification)
        
        # Method 2: Action sequence analysis
        action_verification = self._verify_by_actions(
            task_description,
            actions_taken
        )
        verifications.append(action_verification)
        
        # Method 3: LLM-based verification (if available)
        if self.llm_client:
            llm_verification = self._verify_by_llm(
                task_description,
                actions_taken,
                current_state
            )
            verifications.append(llm_verification)
        
        # Aggregate results
        result = self._aggregate_verifications(verifications)
        
        # Store in history
        self.verification_history.append({
            "timestamp": time.time(),
            "task": task_description,
            "result": result
        })
        
        return result
    
    def _verify_by_screen_state(
        self,
        task_description: str,
        current_state: Dict
    ) -> Dict:
        """Verify completion by analyzing current screen state."""
        evidence = []
        confidence = 0.0
        
        app_name = current_state.get("app", "").lower()
        window_title = current_state.get("window", "").lower()
        task_lower = task_description.lower()
        
        # Check if expected app is open
        expected_apps = self._extract_app_names(task_description)
        if expected_apps:
            app_matches = any(app in app_name for app in expected_apps)
            if app_matches:
                evidence.append(f"Expected app '{app_name}' is open")
                confidence += 0.3
            else:
                evidence.append(f"Expected app not found (got '{app_name}')")
        
        # Check for task-specific keywords
        task_keywords = self._extract_keywords(task_description)
        keyword_matches = sum(
            1 for keyword in task_keywords
            if keyword in window_title or keyword in app_name
        )
        
        if task_keywords and keyword_matches > 0:
            match_ratio = keyword_matches / len(task_keywords)
            evidence.append(f"Found {keyword_matches}/{len(task_keywords)} keywords in screen")
            confidence += 0.3 * match_ratio
        
        # Check for completion indicators
        if "send" in task_lower or "message" in task_lower:
            # For messaging tasks, check if we're still in the app
            if any(msg_app in app_name for msg_app in ["whatsapp", "messages", "telegram"]):
                evidence.append("Messaging app is active")
                confidence += 0.2
        
        if "open" in task_lower:
            # For open tasks, just need the app open
            if expected_apps and any(app in app_name for app in expected_apps):
                evidence.append("App successfully opened")
                confidence = 0.9  # High confidence for simple open tasks
        
        return {
            "method": "screen_state",
            "complete": confidence >= 0.7,
            "confidence": confidence,
            "evidence": evidence
        }
    
    def _verify_by_actions(
        self,
        task_description: str,
        actions_taken: List
    ) -> Dict:
        """Verify completion by analyzing actions taken."""
        evidence = []
        confidence = 0.0
        
        if not actions_taken:
            return {
                "method": "actions",
                "complete": False,
                "confidence": 0.0,
                "evidence": ["No actions taken yet"]
            }
        
        task_lower = task_description.lower()
        
        # Count relevant actions - handle both dict and ActionRecord objects
        vision_actions = 0
        blind_actions = 0
        successful_actions = 0
        
        for action in actions_taken:
            if hasattr(action, 'action_type'):
                if action.action_type == "vision":
                    vision_actions += 1
                elif action.action_type == "blind":
                    blind_actions += 1
                if action.success:
                    successful_actions += 1
            elif isinstance(action, dict):
                if action.get("type") == "vision":
                    vision_actions += 1
                elif action.get("type") == "blind":
                    blind_actions += 1
                if action.get("success", True):
                    successful_actions += 1
        
        evidence.append(f"{successful_actions}/{len(actions_taken)} actions successful")
        
        # Check if expected actions were performed
        expected_action_types = self._get_expected_actions(task_description)
        performed_types = set()
        
        for action in actions_taken:
            # Handle both dict and ActionRecord objects
            if hasattr(action, 'description'):
                action_desc = str(action.description).lower()
            elif isinstance(action, dict):
                action_desc = str(action.get("description", "")).lower()
            else:
                action_desc = str(action).lower()
            
            if "click" in action_desc or "find" in action_desc:
                performed_types.add("click")
            if "type" in action_desc or "search" in action_desc:
                performed_types.add("type")
            if "open" in action_desc:
                performed_types.add("open")
            if "send" in action_desc or "return" in action_desc:
                performed_types.add("send")
        
        matched_actions = performed_types & expected_action_types
        if expected_action_types:
            match_ratio = len(matched_actions) / len(expected_action_types)
            evidence.append(f"Performed {len(matched_actions)}/{len(expected_action_types)} expected action types")
            confidence += 0.5 * match_ratio
        
        # Check if all actions succeeded
        if successful_actions == len(actions_taken) and len(actions_taken) >= 3:
            evidence.append("All actions succeeded")
            confidence += 0.4  # Increased from 0.3
        elif successful_actions == len(actions_taken):
            evidence.append("All actions succeeded (few actions)")
            confidence += 0.3
        else:
            evidence.append(f"{len(actions_taken) - successful_actions} actions failed")
        
        # Boost confidence if we see "send" action for messaging tasks
        if "send" in performed_types and ("message" in task_lower or "send" in task_lower):
            evidence.append("Send action completed for messaging task")
            confidence += 0.3
        
        return {
            "method": "actions",
            "complete": confidence >= 0.65,  # Lowered from 0.7
            "confidence": min(confidence, 1.0),
            "evidence": evidence
        }
    
    def _verify_by_llm(
        self,
        task_description: str,
        actions_taken: List[Dict],
        current_state: Dict
    ) -> Dict:
        """Use LLM to verify task completion."""
        try:
            from ..utils.accessibility_reader import format_ui_for_llm
            
            screen_context = format_ui_for_llm(max_elements=30)
            actions_summary = self._format_actions_summary(actions_taken)
            
            prompt = f"""CRITICAL: Verify if this task is ACTUALLY COMPLETE.

**Task:** {task_description}

**Current Screen:**
- App: {current_state.get('app', 'Unknown')}
- Window: {current_state.get('window', '')}

**Actions Taken:**
{actions_summary}

**Screen State:**
{screen_context}

IMPORTANT: Be STRICT. Only say COMPLETE if you have CLEAR EVIDENCE the task succeeded.

Examples of INCOMPLETE:
- Task: "send message to kushal" but we only clicked search bar (INCOMPLETE - message not sent)
- Task: "open calculator" but Notes app is open (INCOMPLETE - wrong app)
- Task: "search for weather" but still on homepage (INCOMPLETE - no search performed)

Examples of COMPLETE:
- Task: "open Safari" and Safari is the frontmost app (COMPLETE)
- Task: "send message" and we see the message in chat history (COMPLETE)
- Task: "create folder" and folder appears in Finder (COMPLETE)

RESPOND IN THIS FORMAT:
COMPLETE: YES or NO
CONFIDENCE: 0-100%
REASON: [clear explanation with evidence]
MISSING: [if NO, what specific steps are missing - be specific about UI elements]

Your response:"""

            response = self.llm_client.generate(prompt, temperature=0.2).strip()
            
            # Parse response
            is_complete = "COMPLETE: YES" in response.upper()
            confidence = 0.5
            
            if "CONFIDENCE:" in response:
                try:
                    conf_text = response.split("CONFIDENCE:")[1].split("\n")[0].strip()
                    confidence = float(conf_text.replace("%", "")) / 100.0
                except:
                    pass
            
            reason = "LLM verification"
            if "REASON:" in response:
                reason = response.split("REASON:")[1].split("MISSING:")[0].strip()
            
            evidence = [reason]
            
            # Extract missing steps
            next_steps = []
            if not is_complete and "MISSING:" in response:
                missing_text = response.split("MISSING:")[1].strip()
                missing_lines = [line.strip() for line in missing_text.split("\n") if line.strip()]
                evidence.append(f"Missing: {missing_text[:200]}")
                next_steps = missing_lines[:3]  # Max 3 next steps
            
            return {
                "method": "llm",
                "complete": is_complete and confidence >= 0.7,
                "confidence": confidence,
                "evidence": evidence,
                "next_steps": next_steps
            }
            
        except Exception as e:
            logger.error(f"LLM verification failed: {e}")
            return {
                "method": "llm",
                "complete": False,
                "confidence": 0.0,
                "evidence": [f"Error: {str(e)}"]
            }
    
    def _aggregate_verifications(self, verifications: List[Dict]) -> Dict:
        """Aggregate multiple verification results."""
        if not verifications:
            return {
                "complete": False,
                "confidence": 0.0,
                "reason": "No verifications performed",
                "evidence": [],
                "next_steps": []
            }
        
        # Weighted voting
        weights = {"screen_state": 0.2, "actions": 0.3, "llm": 0.5}
        
        weighted_confidence = 0.0
        total_weight = 0.0
        all_evidence = []
        next_steps = []
        
        for verification in verifications:
            method = verification.get("method", "unknown")
            weight = weights.get(method, 0.1)
            confidence = verification.get("confidence", 0.0)
            
            weighted_confidence += confidence * weight
            total_weight += weight
            all_evidence.extend(verification.get("evidence", []))
            
            if not verification.get("complete"):
                next_steps.extend(verification.get("next_steps", []))
        
        final_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.0
        
        # Require GOOD confidence for completion (0.65+) - lowered from 0.75
        is_complete = final_confidence >= 0.65
        
        return {
            "complete": is_complete,
            "confidence": final_confidence,
            "reason": f"Aggregated from {len(verifications)} methods (confidence: {final_confidence:.0%})",
            "evidence": all_evidence,
            "next_steps": list(set(next_steps))[:3]  # Deduplicate and limit
        }
    
    def _extract_app_names(self, task_description: str) -> List[str]:
        """Extract expected app names from task."""
        task_lower = task_description.lower()
        apps = []
        
        app_keywords = [
            "safari", "chrome", "firefox", "calculator", "notes", "finder",
            "whatsapp", "messages", "telegram", "slack", "terminal", "mail",
            "calendar", "photos", "music", "settings"
        ]
        
        for app in app_keywords:
            if app in task_lower:
                apps.append(app)
        
        return apps
    
    def _extract_keywords(self, task_description: str) -> List[str]:
        """Extract important keywords from task."""
        # Remove common words
        stop_words = {"a", "an", "the", "and", "or", "but", "to", "in", "on", "at", "for", "with"}
        words = task_description.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        return keywords[:5]  # Top 5 keywords
    
    def _get_expected_actions(self, task_description: str) -> set:
        """Determine expected action types from task."""
        task_lower = task_description.lower()
        actions = set()
        
        if "open" in task_lower:
            actions.add("open")
        if any(kw in task_lower for kw in ["click", "select", "choose"]):
            actions.add("click")
        if any(kw in task_lower for kw in ["type", "write", "enter", "search"]):
            actions.add("type")
        if any(kw in task_lower for kw in ["send", "submit"]):
            actions.add("send")
        
        return actions
    
    def _format_actions_summary(self, actions: List) -> str:
        """Format actions for LLM prompt."""
        if not actions:
            return "No actions taken"
        
        lines = []
        for i, action in enumerate(actions[-10:], 1):  # Last 10 actions
            # Handle both dict and ActionRecord objects
            if hasattr(action, 'description'):
                desc = action.description
                success = action.success
            elif isinstance(action, dict):
                desc = action.get("description", "Unknown action")
                success = action.get("success", True)
            else:
                desc = str(action)
                success = True
            
            success_icon = "✓" if success else "✗"
            lines.append(f"{i}. {success_icon} {desc}")
        
        return "\n".join(lines)


# Global verifier instance
_verifier = None


def get_verifier(llm_client=None):
    """Get or create global verifier instance."""
    global _verifier
    if _verifier is None:
        _verifier = TaskVerifier(llm_client)
    return _verifier
