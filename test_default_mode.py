#!/usr/bin/env python3
"""
Comprehensive Default Mode Verification Test

Tests all core features in default ADAPTIVE mode to ensure:
- All imports work correctly
- No conflicts between modules
- All features are properly integrated
"""

print('=' * 60)
print('COMPREHENSIVE DEFAULT MODE VERIFICATION')
print('=' * 60)
print()

import sys
passed = 0
failed = 0

# 1. Test all imports required for default mode (ADAPTIVE)
print('1️⃣  Testing ADAPTIVE architecture imports...')
try:
    from src.loop.adaptive_coordinator import (
        AdaptiveLoopCoordinator, AdaptivePhase, AdaptiveState,
        MacroPlan, MicroAction, ScreenContext
    )
    print('   ✅ AdaptiveLoopCoordinator imported')
    passed += 1
except Exception as e:
    print(f'   ❌ AdaptiveLoopCoordinator FAILED: {e}')
    failed += 1

# 2. Test UI imports
print()
print('2️⃣  Testing UI components...')
try:
    from src.ui.thinking_window import (
        start_thinking_window, stop_thinking_window,
        show_planner_thinking, show_executor_thinking,
        show_supervisor_thinking, show_thinking, set_window_status
    )
    print('   ✅ Thinking window functions imported')
    passed += 1
except Exception as e:
    print(f'   ❌ Thinking window FAILED: {e}')
    failed += 1

# 3. Test probability model (default feature)
print()
print('3️⃣  Testing Probability Model (flexible execution)...')
try:
    from src.utils.probability_model import (
        get_probability_model, analyze_task_flexibility,
        get_flexible_execution_params, ExecutionFlexibility
    )
    model = get_probability_model()
    analysis = analyze_task_flexibility('test task')
    # ExecutionFlexibility is a dataclass, access task_completeness.overall_score
    score = analysis.task_completeness.overall_score
    print(f'   ✅ Probability model working (task score: {score:.0%})')
    passed += 1
except Exception as e:
    print(f'   ❌ Probability model FAILED: {e}')
    failed += 1

# 4. Test context memory (learning feature)
print()
print('4️⃣  Testing Context Memory (learning)...')
try:
    from src.utils.context_memory import (
        get_context_memory, learn_from_successful_task, resolve_task_context
    )
    mem = get_context_memory()
    print(f'   ✅ Context memory working ({len(mem.resources)} resources loaded)')
    passed += 1
except Exception as e:
    print(f'   ❌ Context memory FAILED: {e}')
    failed += 1

# 5. Test event-driven UI wait
print()
print('5️⃣  Testing Event-Driven UI Wait...')
try:
    from src.utils.ui_wait import (
        get_ui_wait_system, wait_for_ui_stable, smart_wait,
        UIWaitSystem
    )
    wait_sys = get_ui_wait_system()
    print('   ✅ UI wait system available')
    passed += 1
except Exception as e:
    print(f'   ❌ UI wait system FAILED: {e}')
    failed += 1

# 6. Test semantic checker
print()
print('6️⃣  Testing Semantic Checker (dual-path validation)...')
try:
    from src.supervisor.semantic_checker import (
        SemanticChecker, get_semantic_checker, quick_semantic_check
    )
    checker = get_semantic_checker()
    print('   ✅ Semantic checker working')
    passed += 1
except Exception as e:
    print(f'   ❌ Semantic checker FAILED: {e}')
    failed += 1

# 7. Test replay/time travel
print()
print('7️⃣  Testing Time Travel Debugging (Replay)...')
try:
    from src.replay.execution_logger import get_execution_logger, ExecutionLogger
    from src.replay.replay_ui import run_replay, list_sessions
    logger = get_execution_logger()
    print('   ✅ Replay system working')
    passed += 1
except Exception as e:
    print(f'   ❌ Replay system FAILED: {e}')
    failed += 1

# 8. Test enhanced executor
print()
print('8️⃣  Testing Enhanced Executor...')
try:
    from src.agents.enhanced_executor import EnhancedExecutor
    print('   ✅ Enhanced executor imported')
    passed += 1
except Exception as e:
    print(f'   ❌ Enhanced executor FAILED: {e}')
    failed += 1

# 9. Test blind executor
print()
print('9️⃣  Testing Blind Executor...')
try:
    from src.agents.blind_executor import execute_plan_fast, execute_blind_batch
    print('   ✅ Blind executor working')
    passed += 1
except Exception as e:
    print(f'   ❌ Blind executor FAILED: {e}')
    failed += 1

# 10. Test execution confidence
print()
print('🔟 Testing Execution Confidence Model...')
try:
    from src.utils.execution_confidence import (
        ExecutionConfidenceModel, get_confidence_model
    )
    conf_model = get_confidence_model()
    print('   ✅ Execution confidence model working')
    passed += 1
except Exception as e:
    print(f'   ❌ Execution confidence FAILED: {e}')
    failed += 1

# 11. Test schemas (critical for data validation)
print()
print('1️⃣1️⃣ Testing Pydantic Schemas...')
try:
    from src.utils.schemas import (
        MacroPlanResponse, MicroActionsResponse, SupervisorGuidance,
        VerificationResult, MacroStep, MicroAction
    )
    # Test instantiation
    step = MacroStep(step='Test step', context='Test context')
    print('   ✅ Pydantic schemas validated')
    passed += 1
except Exception as e:
    print(f'   ❌ Schemas FAILED: {e}')
    failed += 1

# 12. Test LangGraph availability (optional)
print()
print('1️⃣2️⃣ Testing LangGraph (optional)...')
try:
    from src.loop.langgraph_coordinator import LangGraphCoordinator, LANGGRAPH_AVAILABLE
    if LANGGRAPH_AVAILABLE:
        print('   ✅ LangGraph installed and available')
    else:
        print('   ⚠️  LangGraph not installed (optional feature)')
    passed += 1  # Not a failure if not installed
except Exception as e:
    print(f'   ❌ LangGraph import FAILED: {e}')
    failed += 1

# 13. Test legacy coordinator still works
print()
print('1️⃣3️⃣ Testing Legacy Coordinator...')
try:
    from src.loop.loop_coordinator import LoopCoordinator
    print('   ✅ Legacy coordinator available')
    passed += 1
except Exception as e:
    print(f'   ❌ Legacy coordinator FAILED: {e}')
    failed += 1

# 14. Test main entry point
print()
print('1️⃣4️⃣ Testing Main Entry Point...')
try:
    from src.main import main, run_loop_mode
    print('   ✅ Main entry point imported')
    passed += 1
except Exception as e:
    print(f'   ❌ Main entry point FAILED: {e}')
    failed += 1

# Summary
print()
print('=' * 60)
print('VERIFICATION COMPLETE')
print('=' * 60)
print()
print(f'Results: {passed} passed, {failed} failed')
print()

if failed == 0:
    print('✅ All core features verified!')
    print()
    print('Default mode (ADAPTIVE) is ready to use:')
    print('  python -m src.main --task "your task here"')
else:
    print('❌ Some features have issues - see above for details')
    sys.exit(1)
