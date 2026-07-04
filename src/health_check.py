"""
Health check for Houdini Agent.

Verifies all required services, models, permissions, and directories
are properly configured before running tasks.

Usage:
    python -m src.health_check
    # or via main.py:
    python -m src.main --health-check
"""
import subprocess
import sys
import os
import shutil
from pathlib import Path
from typing import List, Tuple

# Status constants
OK = "✅"
WARN = "⚠️"
FAIL = "❌"
INFO = "ℹ️"


def check_ollama_installed() -> Tuple[str, str]:
    """Check if Ollama binary is available."""
    if shutil.which("ollama"):
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip() or result.stderr.strip()
            return OK, f"Ollama installed ({version})"
        except Exception:
            return OK, "Ollama binary found"
    return FAIL, "Ollama not installed — get it from https://ollama.ai"


def check_ollama_running() -> Tuple[str, str]:
    """Check if Ollama server is responding."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() == "200":
            return OK, "Ollama server is running"
        return FAIL, f"Ollama server returned HTTP {result.stdout.strip()}"
    except Exception:
        return FAIL, "Ollama server not responding on localhost:11434 — run: ollama serve"


def check_ollama_models() -> List[Tuple[str, str]]:
    """Check if required models are downloaded."""
    results = []
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10
        )
        models_output = result.stdout.lower()
    except Exception:
        return [(FAIL, "Could not list Ollama models")]

    try:
        from config.settings import settings
        required_model = settings.ollama_default_model
    except ImportError:
        required_model = "qwen3-coder:480b-cloud"

    # Check for the primary model (or its base name)
    model_base = required_model.split(":")[0].lower()
    if model_base in models_output or required_model.lower() in models_output:
        results.append((OK, f"Model '{required_model}' available"))
    else:
        results.append((WARN, f"Model '{required_model}' not found — run: ollama pull {required_model}"))

    # Check for embedding model
    if "nomic-embed-text" in models_output:
        results.append((OK, "Embedding model 'nomic-embed-text' available"))
    else:
        results.append((WARN, "Embedding model not found — run: ollama pull nomic-embed-text"))

    return results


def check_macos_accessibility() -> Tuple[str, str]:
    """Check if Accessibility permission is granted (macOS only)."""
    if sys.platform != "darwin":
        return INFO, "Not macOS — accessibility check skipped"
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first process'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return OK, "Accessibility permission granted"
        return FAIL, (
            "Accessibility not granted — go to System Settings > "
            "Privacy & Security > Accessibility and add Terminal/your IDE"
        )
    except Exception as e:
        return WARN, f"Could not check accessibility: {e}"


def check_screen_recording() -> Tuple[str, str]:
    """Check if Screen Recording permission works (macOS only)."""
    if sys.platform != "darwin":
        return INFO, "Not macOS — screen recording check skipped"
    try:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        result = subprocess.run(
            ["screencapture", "-x", path],
            capture_output=True, timeout=5
        )
        file_size = os.path.getsize(path) if os.path.exists(path) else 0
        os.unlink(path)
        if result.returncode == 0 and file_size > 1000:
            return OK, f"Screen recording works ({file_size} bytes captured)"
        return FAIL, (
            "Screen recording may be blocked — go to System Settings > "
            "Privacy & Security > Screen Recording"
        )
    except Exception as e:
        return WARN, f"Could not test screen recording: {e}"


def check_tinyclick_venv() -> Tuple[str, str]:
    """Check if TinyClick virtual environment exists."""
    try:
        from config.settings import settings
        venv_path = settings.tinyclick_venv_path
    except ImportError:
        venv_path = ".tinyclick-venv"

    venv_dir = Path(venv_path)
    if venv_dir.exists() and (venv_dir / "bin" / "python").exists():
        return OK, f"TinyClick venv found at {venv_path}"
    return WARN, f"TinyClick venv not found at {venv_path} (optional — needed for vision actions)"


def check_data_directories() -> List[Tuple[str, str]]:
    """Check if data directories exist or can be created."""
    results = []
    try:
        from config.settings import settings
        dirs = [
            ("data_dir", settings.data_dir),
            ("replay_sessions", settings.replay_sessions_dir),
            ("screenshots", settings.screenshots_dir),
            ("training_sessions", settings.training_sessions_dir),
        ]
    except ImportError:
        base = Path(__file__).parent.parent / "data"
        dirs = [
            ("data_dir", str(base)),
            ("replay_sessions", str(base / "replay_sessions")),
            ("screenshots", str(base / "screenshots")),
            ("training_sessions", str(base / "training_sessions")),
        ]

    for name, path in dirs:
        p = Path(path)
        if p.exists():
            results.append((OK, f"{name}: {path}"))
        else:
            try:
                p.mkdir(parents=True, exist_ok=True)
                results.append((OK, f"{name}: created {path}"))
            except Exception as e:
                results.append((FAIL, f"{name}: cannot create {path} — {e}"))

    return results


def check_python_deps() -> List[Tuple[str, str]]:
    """Check critical Python dependencies."""
    results = []
    critical = ["pydantic", "PIL", "rich"]
    optional = ["pyautogui", "transformers"]

    for mod in critical:
        try:
            __import__(mod)
            results.append((OK, f"{mod} installed"))
        except ImportError:
            results.append((FAIL, f"{mod} not installed — run: pip install -r requirements.txt"))

    for mod in optional:
        try:
            __import__(mod)
            results.append((OK, f"{mod} installed"))
        except ImportError:
            results.append((WARN, f"{mod} not installed (optional)"))

    return results


def check_config() -> Tuple[str, str]:
    """Check if config loads successfully."""
    try:
        from config.settings import settings
        return OK, f"Config loaded (model: {settings.ollama_default_model})"
    except Exception as e:
        return WARN, f"Config failed to load: {e} — using hardcoded defaults"


def run_health_check() -> bool:
    """Run all health checks and print results. Returns True if all critical checks pass."""
    print("\n" + "=" * 60)
    print("  Houdini Agent — Health Check")
    print("=" * 60 + "\n")

    all_results: List[Tuple[str, str]] = []
    critical_fail = False

    # Config
    print("📋 Configuration")
    r = check_config()
    all_results.append(r)
    print(f"  {r[0]} {r[1]}")

    # Ollama
    print("\n🤖 Ollama")
    r = check_ollama_installed()
    all_results.append(r)
    print(f"  {r[0]} {r[1]}")
    if r[0] == FAIL:
        critical_fail = True

    r = check_ollama_running()
    all_results.append(r)
    print(f"  {r[0]} {r[1]}")
    if r[0] == FAIL:
        critical_fail = True

    for r in check_ollama_models():
        all_results.append(r)
        print(f"  {r[0]} {r[1]}")

    # macOS Permissions
    print("\n🔐 Permissions")
    r = check_macos_accessibility()
    all_results.append(r)
    print(f"  {r[0]} {r[1]}")
    if r[0] == FAIL:
        critical_fail = True

    r = check_screen_recording()
    all_results.append(r)
    print(f"  {r[0]} {r[1]}")
    if r[0] == FAIL:
        critical_fail = True

    # Vision
    print("\n👁️  Vision")
    r = check_tinyclick_venv()
    all_results.append(r)
    print(f"  {r[0]} {r[1]}")

    # Directories
    print("\n📁 Data Directories")
    for r in check_data_directories():
        all_results.append(r)
        print(f"  {r[0]} {r[1]}")

    # Python deps
    print("\n🐍 Python Dependencies")
    for r in check_python_deps():
        all_results.append(r)
        print(f"  {r[0]} {r[1]}")
        if r[0] == FAIL:
            critical_fail = True

    # Summary
    ok_count = sum(1 for s, _ in all_results if s == OK)
    warn_count = sum(1 for s, _ in all_results if s == WARN)
    fail_count = sum(1 for s, _ in all_results if s == FAIL)

    print("\n" + "-" * 60)
    print(f"  Results: {ok_count} passed, {warn_count} warnings, {fail_count} failed")

    if critical_fail:
        print(f"  {FAIL} Some critical checks failed — fix them before running tasks")
    elif warn_count > 0:
        print(f"  {WARN} All critical checks passed, but some optional features may be unavailable")
    else:
        print(f"  {OK} All checks passed — ready to go!")
    print("-" * 60 + "\n")

    return not critical_fail


if __name__ == "__main__":
    success = run_health_check()
    sys.exit(0 if success else 1)
