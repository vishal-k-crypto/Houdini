# Cognitive Planning Enhancement Guide

## Overview

The planner prompt has been enhanced with **research-backed cognitive strategies** from psychology and neuroscience to help Gemini 3 Pro plan tasks the way humans naturally solve problems in workplace environments.

## Key Research Foundations

### 1. Cognitive Load Theory (Sweller, 1988)
**Application**: Task complexity determines planning strategy

- **Simple tasks**: Automatic processing, minimal cognitive load → Max batching
- **Complex tasks**: Chunking and working memory management → Phased approach
- **Intrinsic load**: Task difficulty (can't change)
- **Extraneous load**: How we present it (we optimize this)
- **Germane load**: Learning and schema building (pattern recognition)

**In Practice**:
- Routine tasks get single blind batches (low load)
- Research tasks get phases with checkpoints (manage load)
- Creative tasks get frequent feedback (support exploration)

### 2. Problem-Solving Strategies (Newell & Simon, 1972)

**Recognition-Primed Decision Making (Klein, 1993)**:
- Experts recognize patterns and act immediately
- Implementation: Check learned patterns FIRST before planning
- If 85%+ confidence → Execute cached solution

**Means-Ends Analysis**:
- Break problem into subgoals
- Implementation: Identify intermediate states for complex tasks
- Add vision checks at each transition

**Decomposition Principle**:
- Complex problems become manageable when broken down
- Implementation: Hierarchical task breakdown with clear phases

### 3. Working Memory Limitations (Miller, 1956)

**"7 ± 2" Chunking Rule**:
- Humans can hold 5-7 items in working memory
- Implementation: Limit action batches to 5-7 items
- Use meaningful descriptions as memory anchors

**Cognitive Offloading**:
- Use environment to reduce mental load
- Implementation: Leverage system features (Cmd+L auto-selects)
- Let computer handle position/state memory

### 4. Decision-Making Under Uncertainty (Kahneman & Tversky)

**Satisficing (Simon, 1956)**:
- Accept "good enough" solutions quickly
- Implementation: Don't over-optimize simple tasks
- Balance planning time vs execution time

**Bounded Rationality**:
- Make decisions with limited information/time
- Implementation: Use heuristics for speed
- Trust patterns, don't overthink

### 5. Expertise Development (Chi et al., 1981)

**Pattern Recognition**:
- Experts see patterns novices miss
- Implementation: Build pattern library from successful tasks
- Apply schemas to similar situations

**Transfer Learning**:
- Knowledge transfers across similar domains  
- Implementation: Generalize task strategies across contexts
- Identify task families and their approaches

## Task Type Categories & Strategies

### Based on Workplace Research

#### 1. **Routine Tasks** (40-50% of work)
Examples: Email, calendar, file opening
Strategy: Automatic processing
Cognitive Load: Very Low

**Planning Rules**:
- Single blind batch
- Minimal verification
- Trust learned patterns 100%
- Speed over safety

#### 2. **Information Retrieval** (20-30% of work)
Examples: Web search, documentation lookup
Strategy: Satisficing
Cognitive Load: Low-Medium

**Planning Rules**:
- Fast search (blind)
- Single relevance check (vision)
- First good result wins
- Don't perfect, move on

#### 3. **Data Entry** (10-15% of work)
Examples: Forms, configuration, input
Strategy: Sequential processing
Cognitive Load: Medium

**Planning Rules**:
- Section by section
- Verify major milestones
- Tab navigation when possible
- Vision for dynamic elements

#### 4. **Creative Work** (10-15% of work)
Examples: Design, writing, brainstorming
Strategy: Divergent → Convergent
Cognitive Load: High

**Planning Rules**:
- Frequent vision checks
- Shorter action batches
- Support iteration
- Allow exploration

#### 5. **Troubleshooting** (5-10% of work)
Examples: Debugging, problem-solving
Strategy: Hypothesis testing
Cognitive Load: Very High

**Planning Rules**:
- Vision-heavy approach
- Small incremental steps
- Build mental model
- Support backtracking

#### 6. **Workflows** (Variable)
Examples: Publishing, batch processing
Strategy: Goal stack maintenance
Cognitive Load: Variable

**Planning Rules**:
- Clear phase boundaries
- Milestone verification
- Progressive complexity
- Context preservation

## Time-of-Day Adaptations

### Morning (8-9 AM) - High Energy
- User on autopilot
- System fresh and fast
- Maximize blind batching
- Minimal verification

### Focus Time (9 AM-12 PM) - Peak Performance
- User needs efficiency
- Get out of way quickly
- Single-purpose execution
- No exploration

### Post-Lunch (1-3 PM) - Moderate Energy
- Normal planning
- Standard approach
- Balanced strategy

### Late Afternoon (4-6 PM) - Fatigue
- User tired
- Simpler plans needed
- More verification
- Clearer explanations

### Evening - Very Low Energy
- Maximum simplification
- Explicit steps
- Heavy verification
- Assume low focus

## Cognitive Biases We Leverage

### Mental Set (Positive)
✅ Reuse successful patterns aggressively
- Don't reinvent the wheel
- Trust what worked before
- 85%+ confidence = auto-execute

### Functional Fixedness (Overcome)
✅ Use tools optimally
- Cmd+L = select + focus (not just focus)
- Cmd+A + type > delete + type
- Leverage hidden functionality

### Confirmation Bias (Managed)
✅ Trust proven patterns BUT verify new contexts
- High-confidence patterns = trusted
- New situations = exploration
- Balance exploitation vs exploration

### Anchoring & Adjustment
✅ Start with base pattern, modify minimally
- Find similar task
- Adjust for current context
- Preserve what works

## Implementation in Code

### Pattern Priority (Actual Order):
1. **Learned Patterns** (85%+ confidence) → Instant execution
2. **Cached Plans** (exact match) → Quick retrieval
3. **Similar Patterns** (70%+ match) → Adapt and use
4. **LLM Planning** (novel task) → Full cognitive process

### Optimization Loop:
```python
# 1. Try pattern recognition (expertise)
if high_confidence_pattern:
    return cached_solution
    
# 2. Try similar pattern (analogy)
if similar_pattern:
    return adapt_pattern()
    
# 3. Full planning (cognitive effort)
plan = llm_generate_with_cognitive_framework()

# 4. Optimize and learn
plan = optimize_with_action_optimizer()
cache_for_future()
```

## Metrics That Matter

### Efficiency Metrics:
- **Pattern Hit Rate**: % tasks using cached patterns (target: 60%+)
- **Planning Time**: Time to generate plan (target: <500ms)
- **Execution Time**: Total task time (target: minimize)
- **Vision Checks**: Number per task (target: minimize)

### Quality Metrics:
- **Success Rate**: Task completion rate (target: 95%+)
- **User Satisfaction**: Perceived efficiency (qualitative)
- **Cognitive Load**: Subjective effort required (minimize)
- **Learning Rate**: Pattern improvement over time (maximize)

## Future Enhancements

### Planned Additions:
1. **User Modeling**: Learn individual preferences
2. **Context Awareness**: Detect app states automatically
3. **Emotional State**: Adapt to user stress/fatigue
4. **Collaborative Tasks**: Multi-agent coordination
5. **Predictive Planning**: Anticipate next actions

### Research Areas:
- Attention mechanisms in planning
- Memory consolidation for patterns
- Meta-cognitive monitoring
- Adaptive difficulty scaling
- Social learning from other agents

## References

### Core Research:
1. Sweller, J. (1988). "Cognitive Load During Problem Solving"
2. Newell, A. & Simon, H. (1972). "Human Problem Solving"
3. Miller, G. (1956). "The Magical Number Seven, Plus or Minus Two"
4. Klein, G. (1993). "Recognition-Primed Decisions"
5. Chi, M. et al. (1981). "Categorization and Representation of Physics Problems"
6. Kahneman, D. & Tversky, A. (1979). "Prospect Theory"
7. Simon, H. (1956). "Rational Choice and the Structure of the Environment"

### Cognitive Load Research:
- Paas, F. et al. (2003). "Cognitive Load Theory and Instructional Design"
- Chandler, P. & Sweller, J. (1991). "Cognitive Load Theory and the Format of Instruction"

### Problem-Solving Research:
- Anderson, J. (1983). "The Architecture of Cognition"
- Larkin, J. et al. (1980). "Expert and Novice Performance in Solving Physics Problems"

## How to Use This Guide

### For Developers:
1. Read the Quick Decision Framework in the prompt
2. Understand the task type categories
3. Implement pattern matching first
4. Fall back to cognitive framework for novel tasks

### For Prompt Engineers:
1. Maintain the cognitive hierarchy
2. Add examples using task categories
3. Keep heuristics clear and actionable
4. Balance depth with readability

### For Researchers:
1. Test pattern recognition accuracy
2. Measure cognitive load reduction
3. Compare with baseline planning
4. Iterate based on metrics

---

**Last Updated**: January 2026
**Status**: Active Enhancement
**Impact**: Expected 2-3x improvement in planning speed and quality for routine tasks
