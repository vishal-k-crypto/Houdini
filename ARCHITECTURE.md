# System Architecture - Prompt Evolution

## Overview Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     HOUDINI AGENT                            │
│                                                              │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐         │
│  │  PLANNER   │   │  EXECUTOR  │   │ SUPERVISOR │         │
│  │            │   │            │   │            │         │
│  │ Plans      │   │ Executes   │   │ Validates  │         │
│  │ Tasks      │   │ Actions    │   │ Results    │         │
│  └─────┬──────┘   └─────┬──────┘   └─────┬──────┘         │
│        │                │                │                  │
│        └────────────────┼────────────────┘                  │
│                         │                                   │
│                         ▼                                   │
│              ┌─────────────────────┐                        │
│              │  PROMPT SYSTEM      │                        │
│              ├─────────────────────┤                        │
│              │ • Prompt Loader     │                        │
│              │ • Evolution Engine  │                        │
│              │ • Feedback Tracker  │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## Prompt Evolution Flow

```
┌─────────────┐
│  Execute    │
│  Task       │
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│ Load Evolved Prompts    │
│ • planner_prompt.md     │
│ • executor_prompt.md    │
│ • supervisor_prompt.md  │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Component Uses Prompt   │
│ • Planning              │
│ • Execution             │
│ • Validation            │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Record Feedback         │
│ • Success/Failure       │
│ • Error Type            │
│ • Execution Time        │
│ • Actions Taken         │
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Store in feedback_log   │
│ (JSON file)             │
└──────┬──────────────────┘
       │
       ▼
    ┌──────────┐
    │ Failure  │────No───────┐
    │ Rate >   │             │
    │ 20%?     │             │
    └────┬─────┘             │
         │                   │
        Yes                  │
         │                   │
         ▼                   │
┌─────────────────────────┐ │
│ Analyze Failures        │ │
│ • Pattern Detection     │ │
│ • Error Grouping        │ │
│ • Root Cause Analysis   │ │
└──────┬──────────────────┘ │
       │                    │
       ▼                    │
┌─────────────────────────┐ │
│ Generate Improvements   │ │
│ • Create Evolution Note │ │
│ • Add Specific Guidance │ │
│ • Include Examples      │ │
└──────┬──────────────────┘ │
       │                    │
       ▼                    │
┌─────────────────────────┐ │
│ Update Prompt File      │ │
│ • Append to .md file    │ │
│ • Log evolution         │ │
│ • Preserve history      │ │
└──────┬──────────────────┘ │
       │                    │
       └────────────────────┘
              │
              ▼
       ┌─────────────┐
       │  Next Task  │
       │ Uses Evolved│
       │   Prompt    │
       └─────────────┘
```

## Data Flow Diagram

```
┌──────────────────┐
│   User Task      │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│          PROMPT LOADER                   │
│  ┌────────────────────────────────────┐  │
│  │ Load planner_prompt.md             │  │
│  │ Load executor_prompt.md            │  │
│  │ Load supervisor_prompt.md          │  │
│  │ [Cached with TTL]                  │  │
│  └────────────────────────────────────┘  │
└─────────┬────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│        COMPONENT EXECUTION               │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Planner  │→ │ Executor │→ │ Super- │ │
│  │          │  │          │  │ visor  │ │
│  └──────────┘  └──────────┘  └────────┘ │
└─────────┬────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│       FEEDBACK COLLECTION                │
│  ┌────────────────────────────────────┐  │
│  │ Component: "executor"              │  │
│  │ Task: "click button"               │  │
│  │ Success: false                     │  │
│  │ Error: "element_not_found"         │  │
│  │ Time: 2.3s                         │  │
│  └────────────────────────────────────┘  │
└─────────┬────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│      DATA STORAGE                        │
│  ┌────────────────┐  ┌────────────────┐  │
│  │ feedback_log   │  │ task_history   │  │
│  │    .json       │  │    .json       │  │
│  └────────────────┘  └────────────────┘  │
└─────────┬────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│     EVOLUTION ENGINE                     │
│  ┌────────────────────────────────────┐  │
│  │ 1. Detect failure patterns         │  │
│  │ 2. Analyze root causes             │  │
│  │ 3. Generate improvements           │  │
│  │ 4. Update prompt files             │  │
│  │ 5. Log evolution                   │  │
│  └────────────────────────────────────┘  │
└─────────┬────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│    EVOLVED PROMPTS                       │
│  ┌────────────────────────────────────┐  │
│  │ planner_prompt.md v2               │  │
│  │ + Evolution Update 2026-01-13      │  │
│  │   - Better timing guidance         │  │
│  │   - Improved action batching       │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

## Component Interaction

```
     ┌──────────────────────────────────────────┐
     │           PROMPT FILES                   │
     │  (Markdown files with system prompts)   │
     └────────┬─────────────────────────────────┘
              │
              │ Load
              ▼
     ┌──────────────────────────────────────────┐
     │         PROMPT LOADER                    │
     │  • Cache management                      │
     │  • File monitoring                       │
     │  • Auto-reload on changes                │
     └────────┬─────────────────────────────────┘
              │
              │ Provide Prompts
              ▼
     ┌─────────────────────────────────────────────────┐
     │              COMPONENTS                         │
     │                                                 │
     │  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
     │  │ Planner  │  │ Executor │  │Supervisor│     │
     │  │          │  │          │  │          │     │
     │  │ Uses     │  │ Uses     │  │ Uses     │     │
     │  │ Prompt   │  │ Prompt   │  │ Prompt   │     │
     │  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
     │       │             │             │            │
     │       └─────────────┼─────────────┘            │
     │                     │                          │
     └─────────────────────┼──────────────────────────┘
                           │
                           │ Record Feedback
                           ▼
     ┌──────────────────────────────────────────┐
     │       PROMPT EVOLUTION                   │
     │                                          │
     │  ┌────────────────────────────────────┐  │
     │  │  Feedback Tracker                  │  │
     │  │  • Success/Failure rates           │  │
     │  │  • Error patterns                  │  │
     │  │  • Execution metrics               │  │
     │  └────────────┬───────────────────────┘  │
     │               │                          │
     │  ┌────────────▼───────────────────────┐  │
     │  │  Pattern Analyzer                  │  │
     │  │  • Detect failure patterns         │  │
     │  │  • Group similar errors            │  │
     │  │  • Identify trends                 │  │
     │  └────────────┬───────────────────────┘  │
     │               │                          │
     │  ┌────────────▼───────────────────────┐  │
     │  │  Evolution Generator               │  │
     │  │  • Create improvement notes        │  │
     │  │  • Generate new guidelines         │  │
     │  │  • Add examples                    │  │
     │  └────────────┬───────────────────────┘  │
     └───────────────┼──────────────────────────┘
                     │
                     │ Update
                     ▼
     ┌──────────────────────────────────────────┐
     │      PROMPT FILES (Updated)              │
     │  + New Evolution Notes                   │
     │  + Improved Guidelines                   │
     └──────────────────────────────────────────┘
```

## Learning Cycle

```
┌──────────────┐
│   Execution  │
│   (100x)     │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ 20 Failures      │
│ 80 Successes     │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐      ┌─────────────────────┐
│ Failure Pattern  │─────▶│ "element_not_found" │
│ Detection        │      │ occurs 15x          │
└──────┬───────────┘      └─────────────────────┘
       │
       ▼
┌──────────────────┐      ┌─────────────────────┐
│ Root Cause       │─────▶│ Wait times too short│
│ Analysis         │      │ before searching    │
└──────┬───────────┘      └─────────────────────┘
       │
       ▼
┌──────────────────┐      ┌─────────────────────┐
│ Generate         │─────▶│ "Increase waits by  │
│ Solution         │      │  50%, add retry"    │
└──────┬───────────┘      └─────────────────────┘
       │
       ▼
┌──────────────────┐
│ Update Prompt    │
│ with Learning    │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Next Execution   │
│ Uses Evolved     │
│ Prompt           │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Improved Results │
│ 5 Failures       │ ←──┐
│ 95 Successes     │    │
└──────┬───────────┘    │
       │                │
       └────────────────┘
       (Continue Learning)
```

## File Structure

```
houdini-agent/
│
├── prompts/                        # System prompts
│   ├── planner_prompt.md          # ← Evolves automatically
│   ├── executor_prompt.md         # ← Evolves automatically
│   └── supervisor_prompt.md       # ← Evolves automatically
│
├── data/                          # Feedback & logs
│   ├── feedback_log.json         # ← Execution feedback
│   ├── prompt_evolution_log.json # ← Evolution history
│   └── task_history.json         # ← Cached plans
│
├── src/
│   ├── utils/
│   │   ├── prompt_loader.py      # Load prompts
│   │   ├── prompt_evolution.py   # Evolution engine
│   │   ├── prompt_config.py      # Configuration
│   │   └── prompt_stats.py       # Statistics
│   │
│   ├── planner/
│   │   └── gemini_planner.py     # ← Uses planner_prompt
│   │
│   ├── agents/
│   │   └── blind_executor.py     # ← Uses executor_prompt
│   │
│   └── supervisor/
│       └── qwen_validator.py     # ← Uses supervisor_prompt
│
├── examples/
│   └── prompt_system_example.py  # Usage examples
│
└── docs/
    ├── PROMPT_SYSTEM.md          # Full documentation
    ├── IMPLEMENTATION_SUMMARY.md # What was built
    └── QUICK_REFERENCE.md        # Quick commands
```

## Evolution Timeline Example

```
Day 1
├── Initial prompts created
├── 50 tasks executed
└── 10 failures (20% rate)
    └── Trigger evolution #1
        └── Add retry logic

Day 2
├── Evolved prompts used
├── 50 tasks executed
└── 5 failures (10% rate)
    └── Below threshold, no evolution

Day 3
├── 100 tasks executed
└── 8 failures (8% rate)
    └── Below threshold, stable

Day 7
├── 500 total executions
├── 40 total failures (8% rate)
├── 2 prompt evolutions
└── System stabilized
```

## Success Metrics Flow

```
┌─────────────────┐
│ Track Metrics   │
├─────────────────┤
│ • Success Rate  │
│ • Exec Time     │
│ • Error Types   │
│ • Patterns      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│ Calculate Stats │────▶│ Per Component│
│                 │     │ Per Error    │
│                 │     │ Per Time     │
└────────┬────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐
│ Visualize       │
│ (prompt_stats)  │
├─────────────────┤
│ Overall: 92%    │
│ Planner: 95%    │
│ Executor: 90%   │
│ Supervisor: 91% │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Recommendations │
├─────────────────┤
│ ✅ All good     │
│ ⚠️ Needs tests  │
│ ❌ Low rate     │
└─────────────────┘
```
