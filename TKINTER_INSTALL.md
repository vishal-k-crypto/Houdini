# Installing Tkinter for Thinking Window

The thinking window requires Tkinter, which may not be included with all Python installations.

## Check if Tkinter is Available

```bash
python3 -m tkinter
```

If a test window appears, you're all set! If not, follow the installation instructions below.

## macOS Installation

### Using Homebrew (Recommended)

```bash
# For Python 3.14
brew install python-tk@3.14

# For Python 3.13
brew install python-tk@3.13

# For Python 3.12
brew install python-tk@3.12

# Or install for the general python3
brew install python-tk
```

### Alternative: Use System Python

macOS system Python includes Tkinter by default. You can use:

```bash
/usr/bin/python3 -m src.main --task "your task" --loop
```

## Linux Installation

### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install python3-tk
```

### Fedora/RHEL

```bash
sudo dnf install python3-tkinter
```

### Arch Linux

```bash
sudo pacman -S tk
```

## Windows Installation

Tkinter is included with the official Python installer from python.org. If it's missing:

1. Uninstall Python
2. Download from https://www.python.org/downloads/
3. Run installer and ensure "tcl/tk and IDLE" is checked

## Testing Installation

After installation, verify with:

```bash
python3 -c "import tkinter; print('✅ Tkinter available')"
```

## Graceful Degradation

If Tkinter is not available, the agent will still work - the thinking window will simply be disabled with a warning message. All other functionality remains intact.

You'll see:
```
⚠️  Tkinter not available - thinking window disabled
   To enable: brew install python-tk@3.14 (or your Python version)
```

## Troubleshooting

### Error: "No module named '_tkinter'"

This means Tkinter is not installed. Follow the installation instructions above for your OS.

### Error: "TclError: no display name and no $DISPLAY environment variable"

This occurs in headless environments (SSH, CI/CD). Use `--no-thinking-window` flag:

```bash
python -m src.main --task "your task" --loop --no-thinking-window
```

### Window appears but is blank

Try updating Tkinter:
```bash
brew reinstall python-tk@3.14
```

Or restart your terminal after installation.
