#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  AV Teleprompter — macOS Setup Script
#  Run once: bash setup.sh
# ─────────────────────────────────────────────────────────────────

set -e

PYTHON=python3
VENV_DIR=".venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   AV Teleprompter — Setup                ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Check Python ──────────────────────────────────────────────────
if ! command -v $PYTHON &>/dev/null; then
    echo "✗ python3 not found. Install from https://python.org or via Homebrew:"
    echo "  brew install python"
    exit 1
fi
echo "✓ Python $($PYTHON --version)"

# ── Create virtual environment ────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creating virtual environment..."
    $PYTHON -m venv $VENV_DIR
fi
source $VENV_DIR/bin/activate
echo "✓ venv active"

# ── Core deps ─────────────────────────────────────────────────────
echo "→ Installing core dependencies..."
pip install --quiet --upgrade pip
pip install sounddevice numpy

# ── pyobjc for screen-share invisibility ─────────────────────────
echo "→ Installing pyobjc (screen-share invisibility)..."
pip install pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz \
            pyobjc-framework-AppKit

echo ""
echo "✓ All dependencies installed."
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  To run:                                 ║"
echo "║    source .venv/bin/activate             ║"
echo "║    python teleprompter.py                ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── macOS microphone permission note ─────────────────────────────
echo "⚠  macOS Note:"
echo "   On first run, macOS will ask for Microphone permission."
echo "   Grant it in System Settings → Privacy & Security → Microphone."
echo "   If denied, voice-scroll will be disabled (manual mode still works)."
echo ""
