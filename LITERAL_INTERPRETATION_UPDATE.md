# Literal Interpretation Update

## Problem
The agent was overthinking user requests by applying too much "human-like" cognitive reasoning. When user specified "nano banana" as a tool, the agent interpreted this as needing an "AI image generator" instead of literally using "nano banana".

## Root Cause
The planner, executor, and supervisor prompts emphasized human cognitive strategies (cognitive load management, bounded rationality, means-ends analysis, etc.) without prioritizing literal interpretation of explicit user requests.

## Solution
Modified all three agent prompts to prioritize **literal interpretation** for 90% of tasks, reserving complex cognitive strategies only for genuinely ambiguous situations.

## Changes Made

### 1. Planner Prompt ([prompts/planner_prompt.md](prompts/planner_prompt.md))

**Added at the top:**
- **CRITICAL: Literal Interpretation First** section
- Clear rule: "When user specifies a tool/app/term, USE IT EXACTLY AS SPECIFIED"
- Examples showing wrong vs. correct approach
- Decision tree for when to use literal vs. cognitive mode

**Key additions:**
- "Did user specify exact tools/terms?" as first decision point
- 90/10 rule: 90% of tasks need literal execution, 10% need cognitive strategies
- Explicit examples: "nano banana" should be used literally, not replaced

### 2. Executor Prompt ([prompts/executor_prompt.md](prompts/executor_prompt.md))

**Added:**
- **CRITICAL: Execute Literally** section
- Rule: Execute actions EXACTLY as planned - no interpretation
- Reinforces that executor's job is precise execution, not re-planning

### 3. Supervisor Prompt ([prompts/supervisor_prompt.md](prompts/supervisor_prompt.md))

**Added:**
- **CRITICAL: Respect User Intent** section
- Rule: Don't flag user-specified tool names as errors
- Clarifies when to flag issues vs. when to respect user choices
- Examples: "nano banana" is correct if user requested it

## Impact

**Before:**
```
User: "create image using nano banana"
Planner thinks: "They probably mean AI image generator"
Planner plans: Search for "ai image generator"
Result: ❌ Wrong - doesn't use user's specified tool
```

**After:**
```
User: "create image using nano banana"
Planner: User specified "nano banana" - use exactly that
Planner plans: Search for "nano banana" or type "nano banana"
Result: ✅ Correct - uses user's specified tool literally
```

## When to Use Each Mode

### Literal Mode (90% of tasks)
- User provides specific tool/app names
- User gives clear, actionable instructions
- User specifies URLs, search terms, commands
- Task is straightforward

### Cognitive Strategy Mode (10% of tasks)
- User says "I don't know how to..."
- User asks "find the best way to..."
- Task requires multiple steps with unknown dependencies
- User explicitly asks for recommendations

## Testing
To verify the fix works, try:
```bash
python -m src.main --task "create a image using nano banana on covid-19" --loop --supervisor-mode checkpoint
```

The agent should now search for or use "nano banana" literally instead of substituting "AI image generator".

## Philosophy
**AI should be literal by default, smart when needed.**

Human thinking is valuable for complex problem-solving, but most user requests are specific and actionable. The agent should trust the user's expertise about their own tools and workflows, only applying complex reasoning when the path forward is genuinely unclear.
