#!/bin/bash

# Quick setup script for Thinking Window
# This script helps install dependencies and test the thinking window

echo "🚀 Houdini Agent - Thinking Window Setup"
echo "========================================="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3 first."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}' | cut -d. -f1,2)
echo "✅ Found Python $PYTHON_VERSION"
echo ""

# Check if Tkinter is available
echo "🔍 Checking for Tkinter..."
if python3 -c "import tkinter" 2>/dev/null; then
    echo "✅ Tkinter is already installed!"
else
    echo "❌ Tkinter not found"
    echo ""
    
    # Detect OS and provide installation instructions
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "📦 Installing Tkinter for macOS..."
        echo ""
        
        # Check if Homebrew is installed
        if command -v brew &> /dev/null; then
            echo "   Using Homebrew to install python-tk..."
            
            # Determine Python version and install appropriate package
            if [[ $PYTHON_VERSION == "3.14" ]]; then
                brew install python-tk@3.14
            elif [[ $PYTHON_VERSION == "3.13" ]]; then
                brew install python-tk@3.13
            elif [[ $PYTHON_VERSION == "3.12" ]]; then
                brew install python-tk@3.12
            else
                brew install python-tk
            fi
            
            echo ""
            echo "✅ Installation complete!"
        else
            echo "   Homebrew not found. Install with:"
            echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo ""
            echo "   Then run: brew install python-tk@$PYTHON_VERSION"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "📦 To install Tkinter on Linux, run:"
        echo ""
        echo "   Ubuntu/Debian: sudo apt-get install python3-tk"
        echo "   Fedora/RHEL:   sudo dnf install python3-tkinter"
        echo "   Arch Linux:    sudo pacman -S tk"
        echo ""
        exit 1
    else
        echo "📦 Please install Tkinter manually for your OS"
        echo "   See TKINTER_INSTALL.md for detailed instructions"
        exit 1
    fi
fi

# Verify installation
echo ""
echo "🧪 Verifying Tkinter installation..."
if python3 -c "import tkinter; print('✅ Tkinter is working!')" 2>/dev/null; then
    echo ""
    echo "🎉 Success! Thinking Window is ready to use."
    echo ""
    echo "📚 Next steps:"
    echo "   1. Run the demo:        python3 demo_thinking_window.py"
    echo "   2. Use with agent:      python3 -m src.main --task \"your task\" --loop"
    echo "   3. Read documentation:  cat THINKING_WINDOW.md"
    echo ""
else
    echo "❌ Tkinter installation failed or incomplete"
    echo "   Please try manual installation - see TKINTER_INSTALL.md"
    exit 1
fi
