#!/bin/bash
# Download OmniParser V2 model weights from HuggingFace
# Run this once to set up OmniParser for Houdini Agent

set -e

WEIGHTS_DIR="${1:-weights/omniparser}"

echo "📦 Downloading OmniParser V2 weights to $WEIGHTS_DIR..."

# Create weights directory
mkdir -p "$WEIGHTS_DIR"

# Check if huggingface-cli is available
if ! command -v huggingface-cli &> /dev/null; then
    echo "⚠️  huggingface-cli not found. Installing..."
    pip install huggingface-hub
fi

# Download detection model (YOLOv8 fine-tuned)
echo "🔍 Downloading icon detection model (YOLOv8)..."
for f in icon_detect/train_args.yaml icon_detect/model.pt icon_detect/model.yaml; do
    huggingface-cli download microsoft/OmniParser-v2.0 "$f" --local-dir "$WEIGHTS_DIR"
done

# Download caption model (Florence-2)
echo "💬 Downloading icon caption model (Florence-2)..."
for f in icon_caption/config.json icon_caption/generation_config.json icon_caption/model.safetensors; do
    huggingface-cli download microsoft/OmniParser-v2.0 "$f" --local-dir "$WEIGHTS_DIR"
done

# Rename icon_caption to icon_caption_florence (required by OmniParser)
if [ -d "$WEIGHTS_DIR/icon_caption" ] && [ ! -d "$WEIGHTS_DIR/icon_caption_florence" ]; then
    mv "$WEIGHTS_DIR/icon_caption" "$WEIGHTS_DIR/icon_caption_florence"
fi

echo ""
echo "✅ OmniParser weights downloaded successfully!"
echo ""
echo "📁 Weights location: $WEIGHTS_DIR"
echo "   - icon_detect/model.pt (YOLOv8)"
echo "   - icon_caption_florence/ (Florence-2)"
echo ""
echo "🚀 OmniParser is now ready to use!"
echo "   It will automatically activate when:"
echo "   - Processing non-accessible apps (Adobe, Electron, etc.)"
echo "   - macOS Accessibility API returns 0 elements"
