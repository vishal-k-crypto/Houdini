"""
Prompt Evolution Configuration

Customize how the prompt evolution system behaves.
"""

# Evolution Triggers
EVOLUTION_CONFIG = {
    # Minimum failures before considering evolution
    "min_failures_for_evolution": 5,
    
    # Failure rate threshold (0.0 to 1.0)
    # 0.2 = 20% failure rate triggers evolution
    "failure_rate_threshold": 0.2,
    
    # Window size for calculating failure rate
    "failure_rate_window": 100,
    
    # Minimum executions before evolution is allowed
    # Prevents premature evolution from small sample size
    "min_executions_before_evolution": 10,
    
    # Cool-down period between evolutions (seconds)
    # Prevents too-frequent prompt updates
    "evolution_cooldown": 3600,  # 1 hour
    
    # Maximum evolutions per component
    # Set to None for unlimited
    "max_evolutions_per_component": None,
    
    # Auto-save feedback after N executions
    "feedback_save_interval": 10,
}

# Component-Specific Settings
COMPONENT_CONFIG = {
    "planner": {
        "enabled": True,
        "failure_rate_threshold": 0.2,  # Override global setting
        "priority_error_types": [
            "parse_error",
            "invalid_plan",
            "action_format_error"
        ]
    },
    
    "executor": {
        "enabled": True,
        "failure_rate_threshold": 0.25,  # Executor can tolerate slightly more failures
        "priority_error_types": [
            "element_not_found",
            "timeout",
            "action_execution_failed"
        ]
    },
    
    "supervisor": {
        "enabled": True,
        "failure_rate_threshold": 0.15,  # Supervisor should be very accurate
        "priority_error_types": [
            "validation_error",
            "false_positive",
            "false_negative"
        ]
    }
}

# Prompt Caching Settings
CACHE_CONFIG = {
    # Enable prompt caching
    "enabled": True,
    
    # Cache invalidation time (seconds)
    # Set to None to cache indefinitely
    "cache_ttl": 300,  # 5 minutes
    
    # Auto-reload prompts when files change
    "auto_reload": True,
    
    # Check for file changes every N seconds
    "file_check_interval": 60,
}

# Logging Settings
LOGGING_CONFIG = {
    # Log all feedback to file
    "log_feedback": True,
    
    # Log evolution events
    "log_evolution": True,
    
    # Detailed logging (includes analysis details)
    "verbose": False,
    
    # Log file rotation
    "max_feedback_entries": 10000,
    "max_evolution_entries": 1000,
}

# Analysis Settings
ANALYSIS_CONFIG = {
    # Minimum occurrences to identify a pattern
    "pattern_min_occurrences": 3,
    
    # Error type grouping
    # Similar errors grouped together for analysis
    "error_type_groups": {
        "element_issues": [
            "element_not_found",
            "element_not_clickable",
            "element_not_visible"
        ],
        "timing_issues": [
            "timeout",
            "premature_action",
            "slow_response"
        ],
        "format_issues": [
            "parse_error",
            "invalid_format",
            "malformed_json"
        ]
    },
    
    # Confidence thresholds
    "high_confidence_threshold": 0.8,
    "low_confidence_threshold": 0.4,
}

# Prompt Template Settings
TEMPLATE_CONFIG = {
    # Evolution note template
    "evolution_note_template": """
## Evolution Update - {timestamp}

**Failure Analysis**: {failure_count} failures analyzed
{patterns_section}
{errors_section}
{improvements_section}
""",
    
    # Include timestamps in evolution notes
    "include_timestamps": True,
    
    # Include failure counts
    "include_failure_counts": True,
    
    # Include detailed error breakdown
    "include_error_breakdown": True,
}

# Feature Flags
FEATURES = {
    # Enable automatic evolution
    "auto_evolution": True,
    
    # Enable A/B testing (future feature)
    "ab_testing": False,
    
    # Enable cross-component learning
    "cross_component_learning": False,
    
    # Enable success pattern learning (not just failures)
    "success_pattern_learning": False,
    
    # Enable prompt compression (remove outdated rules)
    "prompt_compression": False,
}


def get_config(section: str = None):
    """
    Get configuration section.
    
    Args:
        section: Configuration section name
                 ("evolution", "component", "cache", "logging", "analysis", "template", "features")
                 If None, returns all config
    
    Returns:
        Configuration dictionary
    """
    all_config = {
        "evolution": EVOLUTION_CONFIG,
        "component": COMPONENT_CONFIG,
        "cache": CACHE_CONFIG,
        "logging": LOGGING_CONFIG,
        "analysis": ANALYSIS_CONFIG,
        "template": TEMPLATE_CONFIG,
        "features": FEATURES,
    }
    
    if section:
        return all_config.get(section, {})
    return all_config


def get_component_config(component: str):
    """Get configuration for a specific component."""
    return COMPONENT_CONFIG.get(component, {})


def is_evolution_enabled(component: str = None):
    """Check if evolution is enabled globally or for a component."""
    if not FEATURES["auto_evolution"]:
        return False
    
    if component:
        return COMPONENT_CONFIG.get(component, {}).get("enabled", True)
    
    return True


# Load custom config if exists
try:
    from pathlib import Path
    custom_config_path = Path(__file__).parent.parent.parent / "config" / "prompt_evolution_custom.py"
    if custom_config_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("custom_config", custom_config_path)
        custom_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(custom_config)
        
        # Override with custom settings
        if hasattr(custom_config, "EVOLUTION_CONFIG"):
            EVOLUTION_CONFIG.update(custom_config.EVOLUTION_CONFIG)
        if hasattr(custom_config, "COMPONENT_CONFIG"):
            COMPONENT_CONFIG.update(custom_config.COMPONENT_CONFIG)
        # ... etc for other configs
except Exception:
    pass  # No custom config or loading failed
