# How to Use the New Comprehensive Instructions

## Quick Start

The system now automatically uses the comprehensive instructions. Just run tasks as normal:

```bash
python -m src.main --task "create image using nano banana on covid-19" --loop --supervisor-mode checkpoint
```

## What Changed

### Before
- Agents searched literally for "nano banana" 
- No understanding that it's a Gemini feature
- Too much "human thinking" for simple tasks

### After
- Agents understand "nano banana" is Gemini's image generation
- Plan: Open Gemini → Use image generation feature
- Contextual intelligence without over-thinking

## Key Improvements

### 1. Tool Knowledge
The planner now knows where tools live:
- **"nano banana"** → Gemini feature at gemini.google.com
- **"Perplexity"** → Search engine at perplexity.ai
- **"ChatGPT"** → AI assistant at chat.openai.com
- **"VS Code"** → Desktop app via Spotlight

### 2. Smart Interpretation
Two-mode operation:
- **Literal Mode** (90%): User says "open Safari" → Opens Safari
- **Contextual Mode** (10%): User says "use nano banana" → Opens Gemini first

### 3. Comprehensive Patterns
- 20+ reusable planning patterns
- 100+ macOS shortcuts documented
- Timing patterns for all major apps
- Learning and adaptation built-in

## Test Cases

### Image Creation with Nano Banana
```bash
python -m src.main --task "create image using nano banana showing a futuristic city"
```
**Expected:** Opens Gemini → Generates image

### Search with Specific Tool
```bash
python -m src.main --task "search with Perplexity about machine learning"
```
**Expected:** Opens Perplexity → Searches query

### AI Question
```bash
python -m src.main --task "ask Gemini to explain quantum physics"
```
**Expected:** Opens Gemini → Asks question

### Open and Navigate
```bash
python -m src.main --task "open Safari and go to youtube.com"
```
**Expected:** Opens Safari → Navigates to YouTube

## How It Works

### Architecture
```
User Task
    ↓
Planner (reads comprehensive instructions - Part 1)
    ↓
Creates optimized plan with tool knowledge
    ↓
Executor (reads comprehensive instructions - Part 2)
    ↓
Executes plan precisely
    ↓
Supervisor (reads comprehensive instructions - Part 3)
    ↓
Validates execution, respects user intent
```

### Automatic Loading
The `prompt_loader` automatically:
1. Reads `comprehensive_agent_instructions.md`
2. Extracts relevant section for each agent
3. Caches for performance
4. No manual configuration needed

## Troubleshooting

### If agent still searches literally
- Make sure comprehensive file exists: `prompts/comprehensive_agent_instructions.md`
- Check file size: should be ~101KB
- Try force reload: Add `force_reload=True` in code

### If getting errors
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check Python version: `python3 --version` (need 3.8+)
- Review logs in execution output

### To verify instructions loaded
```bash
python3 test_comprehensive_simple.py
```

Expected output:
- ✓ File exists
- ✓ All 3 parts detected
- ✓ Content verified

## Advanced Usage

### Customize Instructions
Edit `prompts/comprehensive_agent_instructions.md`:
- Part 1 (lines 1-1500): Planner instructions
- Part 2 (lines 1500-2800): Executor instructions  
- Part 3 (lines 2800-4000): Supervisor instructions

Changes take effect immediately (cached, but reloads on restart).

### Add New Tool Knowledge
In Part 1, add to Section 2 (Tool Ecosystem Knowledge Base):

```markdown
#### My New Tool
- **What it is**: Description
- **Location**: URL or app name
- **How to access**: Steps to open/use
- **Usage pattern**: Example task → Plan
```

### Monitor Learning
The system learns optimal timing and patterns:
- Check `data/task_history.json` for cached plans
- Review `data/patterns.json` for learned patterns
- Inspect `data/feedback_log.json` for improvements

## File Structure

```
prompts/
├── comprehensive_agent_instructions.md  ← Main instruction file (101KB)
├── planner_prompt.md                    ← Fallback (old)
├── executor_prompt.md                   ← Fallback (old)
└── supervisor_prompt.md                 ← Fallback (old)

src/utils/
└── prompt_loader.py                     ← Loads & extracts instructions

data/
├── task_history.json                    ← Cached successful plans
├── patterns.json                        ← Learned patterns
└── feedback_log.json                    ← Learning data
```

## Performance

- **File Size**: 101KB
- **Lines**: 3,953
- **Load Time**: <100ms (first load), <1ms (cached)
- **Memory**: ~100KB per agent instance

## Future Enhancements

Want to add more?
1. **More Tools**: Add to Section 2.2-2.4 in Part 1
2. **More Patterns**: Add to Section 8 (Pattern Library) in Part 1
3. **Better Timing**: Edit Section 5.2-5.4 in Part 2
4. **Stricter Validation**: Edit Section 2 in Part 3

## Support

Questions? Check:
- `COMPREHENSIVE_INSTRUCTIONS_IMPLEMENTATION.md` - Full implementation details
- `comprehensive_agent_instructions.md` - The actual instructions
- GitHub issues or discussions

---

**Ready to use!** The system is now much smarter about understanding user intent and tool locations.
