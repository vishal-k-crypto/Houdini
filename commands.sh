#!/bin/bash
# Houdini Agent - Example Commands
# Run from the houdini-agent directory

# ============================================
# ACTIVATION (Run this first!)
# ============================================
# source .venv/bin/activate

# Or use this one-liner:
# cd /Users/letsfuck/Desktop/Houdini/houdini-agent && source .venv/bin/activate

# ============================================
# BASIC USAGE
# ============================================

# Plan only (don't execute actions)
python -m src.main --task "open calculator" --no-execute

# Full execution with 5 steps per subtask
python -m src.main --task "open whatsapp" --steps 5

# ============================================
# LOOP MODE (NEW!) - Continuous State Awareness
# ============================================

# Basic loop mode - model always knows what it's doing
python -m src.main --task "open Safari and search for weather" --loop

# Loop mode without supervisor (faster, less monitoring)
python -m src.main --task "open calculator" --loop --no-supervisor

# Loop mode with checkpoint-based supervision (check after each batch)
python -m src.main --task "open Chrome and search Google" --loop --supervisor-mode checkpoint

# ============================================
# APPLICATION TASKS
# ============================================

# Open applications
python -m src.main --task "open Safari"
python -m src.main --task "open Finder"
python -m src.main --task "open Notes"
python -m src.main --task "open Terminal"
python -m src.main --task "open System Preferences"

# ============================================
# BROWSER TASKS
# ============================================

# Web navigation
python -m src.main --task "open Chrome and go to google.com"
python -m src.main --task "open Safari and search for weather"
python -m src.main --task "open Firefox and go to youtube.com"

# ============================================
# FILE OPERATIONS
# ============================================

# Finder tasks
python -m src.main --task "open Finder and create a new folder on desktop"
python -m src.main --task "open Downloads folder"

# ============================================
# PRODUCTIVITY TASKS
# ============================================

# Notes
python -m src.main --task "open Notes and create a new note"

# Calendar
python -m src.main --task "open Calendar"

# Messages
python -m src.main --task "open Messages"

# ============================================
# COMPLEX MULTI-STEP TASKS (Use Loop Mode!)
# ============================================

# Multi-app workflow with loop mode for better state tracking
python -m src.main --task "open Chrome, go to gmail.com, and compose a new email" --loop

# Research task with continuous awareness
python -m src.main --task "open Safari, search for Python tutorials, and open the first result" --loop

# ============================================
# DEBUGGING OPTIONS
# ============================================

# Limit steps for testing
python -m src.main --task "open calculator" --steps 3

# View help
python -m src.main --help
