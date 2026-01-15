# Adaptive Architecture - Macro/Micro with Real-Time Evolution

## Overview

The new adaptive architecture separates concerns into three distinct roles:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     HOUDINI ADAPTIVE AGENT                           │
│                                                                      │
│  ┌──────────────────┐                                               │
│  │  MACRO PLANNER   │ ─── High-level task understanding            │
│  │  (Strategic)     │     "Open browser, navigate, search"         │
│  └────────┬─────────┘                                               │
│           │                                                         │
│           ▼                                                         │
│  ┌──────────────────┐   ┌──────────────────┐                       │
│  │  MICRO EXECUTOR  │◄──│  SCREEN CONTEXT  │                       │
│  │  (Tactical)      │   │  (App, Window,   │                       │
│  │                  │   │   UI Elements)   │                       │
│  │  Generates:      │   └──────────────────┘                       │
│  │  hotkey, type,   │                                               │
│  │  click, wait     │                                               │
│  └────────┬─────────┘                                               │
│           │                                                         │
│           │ ◄──── "I'm stuck" / "Is this done?"                    │
│           │                                                         │
│           ▼                                                         │
│  ┌───────────────────────────────────────┐                         │
│  │       ADAPTIVE SUPERVISOR              │                         │
│  │  (Overseer + Quality Control)          │                         │
│  │                                        │                         │
│  │  • Handles randomness/unexpected       │                         │
│  │  • Guides executor when stuck          │                         │
│  │  • Verifies task completion            │                         │
│  │  • Takes over planning if needed       │                         │
│  │  • Enables real-time task evolution    │                         │
│  └───────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Principles

### 1. Separation of Abstraction Levels

**Macro Planner** (Strategic)
- Understands the overall goal
- Breaks task into logical phases
- Does NOT specify keyboard shortcuts or detailed actions
- Example: "Open WhatsApp" → not "Cmd+Space, type WhatsApp, Enter"

**Micro Executor** (Tactical)
- Takes one macro step at a time
- Analyzes current screen state
- Generates specific cursor/keyboard actions
- Knows when to ask for help

**Adaptive Supervisor** (Oversight)
- Monitors for unexpected situations
- Guides executor when needed
- Verifies actual completion
- Can replan in real-time

### 2. Real-Time Adaptation

The system can evolve the task in real-time:

```
Macro Plan: [Step A] → [Step B] → [Step C]
                              ↓
                    Verification: INCOMPLETE
                              ↓
                    Supervisor Evolves Task
                              ↓
Evolved Plan: [Step A] → [Step B] → [Step C] → [Step D] → [Step E]
```

### 3. Handling Randomness

When unexpected things happen:

```
Expected: WhatsApp main window
Got: Permission dialog

Executor: "I'm stuck, screen doesn't match"
         ↓
Supervisor: "Close the dialog with Escape, then continue"
         ↓
Executor: Executes supervisor's guidance
         ↓
Back to normal flow
```

## Execution Flow

```
┌─────────────────┐
│  User Task      │
│  "Send msg..."  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PHASE: PLANNING │
│                 │
│ Macro Planner   │
│ generates high- │
│ level steps     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    PHASE: EXECUTING                          │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ For each Macro Step:                                 │    │
│  │                                                      │    │
│  │  1. Capture screen context                          │    │
│  │  2. Generate micro actions                          │    │
│  │  3. Execute actions                                 │    │
│  │  4. If stuck → ask supervisor                       │    │
│  │  5. Move to next macro step                         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Screen doesn't                    Executor                  │
│  match expected? ─────────────────► uncertain? ────────┐    │
│                                                         │    │
│                    ┌────────────────────────────────────┘    │
│                    ▼                                         │
│          ┌─────────────────────┐                            │
│          │ PHASE: SUPERVISOR   │                            │
│          │      GUIDE          │                            │
│          │                     │                            │
│          │ Analyze situation   │                            │
│          │ Provide guidance    │                            │
│          │ or skip/abort       │                            │
│          └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│PHASE: VERIFYING │
│                 │
│ Supervisor      │
│ checks if task  │
│ is ACTUALLY     │
│ complete        │
└────────┬────────┘
         │
    ┌────┴────┐
    │Complete?│
    └────┬────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌───────────────┐
│ DONE  │  │PHASE: EVOLVING│
│  ✓    │  │               │
└───────┘  │ Supervisor    │
           │ adds new      │
           │ steps based   │
           │ on what's     │
           │ missing       │
           └───────┬───────┘
                   │
                   └──────────► Back to EXECUTING
```

## Usage

```bash
# Default: Uses new adaptive architecture
python -m src.main --task "send a message to kushal on whatsapp"

# Use legacy architecture
python -m src.main --task "your task" --legacy
```

## Prompts

Each component has a detailed prompt:

- `prompts/macro_planner_prompt.md` - Strategic planning guidelines
- `prompts/micro_executor_prompt.md` - Tactical action generation
- `prompts/adaptive_supervisor_prompt.md` - Oversight and adaptation

## Key Advantages

1. **Handles Unpredictability**: Pop-ups, crashes, unexpected UI - supervisor handles it
2. **Never Gets Stuck**: If executor is lost, supervisor guides or replans
3. **Verifies Completion**: Doesn't just assume success - actually checks
4. **Real-Time Evolution**: Can adapt and extend task based on what it sees
5. **Clear Separation**: Each component has a clear, focused responsibility
6. **Learning Opportunity**: Supervisor notes can be used for future improvements

## Example Execution

Task: "Send 'Hello' to John on WhatsApp"

```
[PLANNER] Macro steps:
  1. Open WhatsApp application
  2. Find and select contact John
  3. Type and send the message

[EXECUTOR] Step 1: Open WhatsApp
  Screen: Finder - Desktop
  Generating micro actions...
  → hotkey: command+space (Open Spotlight)
  → type: WhatsApp
  → key: return
  → wait: 1.5s
  ✓ Executed

[EXECUTOR] Step 2: Find contact John
  Screen: WhatsApp - Chats
  Generating micro actions...
  → hotkey: command+f (Open search)
  → type: John
  → wait: 0.5s
  → key: return
  ✓ Executed

[EXECUTOR] Step 3: Send message
  Screen: WhatsApp - John
  Generating micro actions...
  → type: Hello
  → key: return
  ✓ Executed

[SUPERVISOR] Verifying completion...
  Screen shows: "Hello" in chat with John, sent indicator visible
  Confidence: 95%
  ✓ COMPLETE
```

## Error Recovery Example

```
[EXECUTOR] Step 2: Find contact John
  Screen: WhatsApp - Notification Permission
  ⚠️ Screen doesn't match expected
  Requesting supervisor guidance...

[SUPERVISOR] Intervention:
  Reason: Unexpected permission dialog
  Decision: GUIDE
  Actions: [key: escape, wait: 0.5]
  Note: "WhatsApp shows permission dialogs on first launch"

[EXECUTOR] Executing supervisor guidance...
  → key: escape
  → wait: 0.5s
  ✓ Dialog closed

[EXECUTOR] Retrying Step 2...
  Screen: WhatsApp - Chats
  Now matches expected context
  Continuing...
```
