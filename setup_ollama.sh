#!/bin/bash
# Setup script for Ollama with Qwen 3 Coder model

echo "🚀 Setting up Houdini Agent with Ollama Qwen 3 Coder"
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not found. Please install it first:"
    echo "   Visit: https://ollama.ai"
    echo "   Or run: brew install ollama"
    exit 1
fi

echo "✅ Ollama found"
ollama --version

echo ""
echo "📦 Pulling Qwen 2.5 Coder 32B model..."
echo "   (This may take a while depending on your connection)"
ollama pull qwen2.5-coder:32b

echo ""
echo "✅ Setup complete!"
echo ""
echo "🎯 Usage:"
echo "   1. Local Ollama (32B model):"
echo "      python -m src.main --task \"your task\" --loop"
echo ""
echo "   2. Ollama Cloud (480B model - when available):"
echo "      python -m src.main --task \"your task\" --loop \\"
echo "         --model qwen3-coder:480b \\"
echo "         --cloud-endpoint https://cloud.ollama.ai"
echo ""
echo "🧠 Executor History:"
echo "   The executor now maintains a history of previous operations"
echo "   This context is automatically used by the planner for better decisions"
echo "   History is stored in: data/executor_history.json"
echo ""
echo "💡 Tips:"
echo "   - The 32B model runs locally and is fast"
echo "   - The 480B model (cloud) provides better reasoning but requires cloud access"
echo "   - Supervisor tracks all executions and learns from patterns"
