"""
Prompt Loader - Centralized system for loading and managing component prompts.

This module provides a unified interface for accessing prompts used by the
Planner, Executor, and Supervisor components. It supports:
- Loading prompts from markdown files (individual or comprehensive)
- Caching for performance
- Version tracking
- Dynamic reloading for evolved prompts
- Extraction of specific sections from comprehensive instructions
"""

from pathlib import Path
from typing import Dict, Optional
import re
from ..utils.logging import logger

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
COMPREHENSIVE_INSTRUCTIONS_FILE = "comprehensive_agent_instructions.md"


class PromptLoader:
    """
    Manages loading and caching of system prompts.
    
    Features:
    - Lazy loading of prompts
    - Automatic cache invalidation
    - Support for prompt evolution
    - Fallback to embedded prompts
    - Extraction from comprehensive instructions file
    """
    
    def __init__(self, prompts_dir: Path = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}
        self._versions: Dict[str, int] = {}
        self.comprehensive_file = self.prompts_dir / COMPREHENSIVE_INSTRUCTIONS_FILE
        
        # Ensure prompts directory exists
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
    
    def _extract_section_from_comprehensive(self, component: str) -> Optional[str]:
        """
        Extract a specific agent's section from comprehensive instructions.
        
        Args:
            component: "planner", "executor", or "supervisor"
        
        Returns:
            The extracted section or None if not found
        """
        if not self.comprehensive_file.exists():
            return None
        
        try:
            with open(self.comprehensive_file, 'r') as f:
                content = f.read()
            
            # Define section markers for each component
            section_markers = {
                "planner": (
                    r"# PART 1: PLANNER AGENT COMPREHENSIVE INSTRUCTIONS",
                    r"# PART 2: EXECUTOR AGENT COMPREHENSIVE INSTRUCTIONS"
                ),
                "executor": (
                    r"# PART 2: EXECUTOR AGENT COMPREHENSIVE INSTRUCTIONS",
                    r"# PART 3: SUPERVISOR AGENT COMPREHENSIVE INSTRUCTIONS"
                ),
                "supervisor": (
                    r"# PART 3: SUPERVISOR AGENT COMPREHENSIVE INSTRUCTIONS",
                    r"# COMPREHENSIVE INSTRUCTIONS SUMMARY"
                )
            }
            
            if component not in section_markers:
                return None
            
            start_marker, end_marker = section_markers[component]
            
            # Find the section
            start_match = re.search(start_marker, content)
            end_match = re.search(end_marker, content)
            
            if start_match and end_match:
                section = content[start_match.start():end_match.start()].strip()
                logger.info(f"📖 Extracted {component} section from comprehensive instructions ({len(section)} chars)")
                return section
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract {component} from comprehensive instructions: {e}")
            return None
    
    def load_prompt(self, component: str, force_reload: bool = False, use_comprehensive: bool = True) -> str:
        """
        Load a component's prompt.
        
        Args:
            component: "planner", "executor", or "supervisor"
            force_reload: Force reload from disk (bypass cache)
            use_comprehensive: Try comprehensive instructions first, then individual files
        
        Returns:
            The prompt text as a string
        """
        # Check cache first
        if not force_reload and component in self._cache:
            return self._cache[component]
        
        prompt_text = None
        
        # Try comprehensive instructions first (if enabled)
        if use_comprehensive:
            prompt_text = self._extract_section_from_comprehensive(component)
            if prompt_text:
                self._cache[component] = prompt_text
                self._versions[component] = int(self.comprehensive_file.stat().st_mtime)
                return prompt_text
        
        # Fall back to individual prompt file
        prompt_file = self.prompts_dir / f"{component}_prompt.md"
        
        if prompt_file.exists():
            try:
                with open(prompt_file, 'r') as f:
                    prompt_text = f.read()
                
                # Cache the prompt
                self._cache[component] = prompt_text
                
                # Track version (based on file modification time)
                mtime = prompt_file.stat().st_mtime
                self._versions[component] = int(mtime)
                
                logger.debug(f"Loaded {component} prompt from individual file ({len(prompt_text)} chars)")
                return prompt_text
                
            except Exception as e:
                logger.error(f"Failed to load prompt for {component}: {e}")
        
        # Last resort: fallback prompt
        logger.warning(f"Using fallback prompt for {component}")
        return self._get_fallback_prompt(component)
    
    def get_planner_prompt(self) -> str:
        """Get the planner system prompt."""
        return self.load_prompt("planner")
    
    def get_executor_prompt(self) -> str:
        """Get the executor system prompt."""
        return self.load_prompt("executor")
    
    def get_supervisor_prompt(self) -> str:
        """Get the supervisor system prompt."""
        return self.load_prompt("supervisor")
    
    def reload_all(self):
        """Reload all prompts from disk (useful after evolution)."""
        for component in ["planner", "executor", "supervisor"]:
            self.load_prompt(component, force_reload=True)
        logger.info("♻️ Reloaded all prompts")
    
    def check_for_updates(self) -> Dict[str, bool]:
        """
        Check if any prompts have been updated on disk.
        
        Returns:
            Dict mapping component names to update status (True if updated)
        """
        updates = {}
        
        for component in ["planner", "executor", "supervisor"]:
            prompt_file = self.prompts_dir / f"{component}_prompt.md"
            
            if not prompt_file.exists():
                updates[component] = False
                continue
            
            current_mtime = int(prompt_file.stat().st_mtime)
            cached_version = self._versions.get(component, 0)
            
            updates[component] = current_mtime > cached_version
        
        return updates
    
    def _get_fallback_prompt(self, component: str) -> str:
        """
        Provide a minimal fallback prompt if file not found.
        
        This ensures the system can still function even if prompt files are missing.
        """
        fallbacks = {
            "planner": """You are a task planning agent. Break down the user's task into actionable steps.
Output a JSON array of action batches with types "blind" (keyboard shortcuts) or "vision" (screen-dependent actions).
Batch blind actions together for speed. Use macOS shortcuts: Cmd+Space for Spotlight, Cmd+T for new tab, etc.""",
            
            "executor": """You are an execution agent. Execute actions precisely as planned.
For blind actions: use hotkey:cmd,space / type:text / key:return / wait:seconds format.
For vision actions: analyze accessibility tree and execute clicks.
Report success/failure clearly.""",
            
            "supervisor": """You are a validation agent. Verify that actions are logically correct.
Check: action makes sense for task, prerequisites met, timing appropriate.
Output: {"approved": true/false, "reason": "...", "suggestion": "..."}"""
        }
        
        return fallbacks.get(component, "You are an AI assistant. Help complete the task.")
    
    def get_prompt_info(self, component: str) -> Dict[str, any]:
        """
        Get metadata about a component's prompt.
        
        Returns:
            Dict with prompt info (size, version, last_updated, etc.)
        """
        prompt_file = self.prompts_dir / f"{component}_prompt.md"
        
        if not prompt_file.exists():
            return {
                "exists": False,
                "component": component,
                "path": str(prompt_file)
            }
        
        stat = prompt_file.stat()
        
        return {
            "exists": True,
            "component": component,
            "path": str(prompt_file),
            "size_bytes": stat.st_size,
            "size_kb": round(stat.st_size / 1024, 2),
            "last_modified": stat.st_mtime,
            "cached": component in self._cache,
            "version": self._versions.get(component, 0)
        }
    
    def clear_cache(self):
        """Clear the prompt cache (forces reload on next access)."""
        self._cache.clear()
        logger.debug("Cleared prompt cache")
    
    def get_all_prompts_info(self) -> Dict[str, Dict]:
        """Get info for all component prompts."""
        return {
            component: self.get_prompt_info(component)
            for component in ["planner", "executor", "supervisor"]
        }


# Global singleton instance
prompt_loader = PromptLoader()


# Convenience functions
def get_planner_prompt() -> str:
    """Get the planner system prompt."""
    return prompt_loader.get_planner_prompt()


def get_executor_prompt() -> str:
    """Get the executor system prompt."""
    return prompt_loader.get_executor_prompt()


def get_supervisor_prompt() -> str:
    """Get the supervisor system prompt."""
    return prompt_loader.get_supervisor_prompt()


def reload_prompts():
    """Reload all prompts from disk."""
    prompt_loader.reload_all()
