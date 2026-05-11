#!/usr/bin/env bash
# Quick-start: create venv with uv and install the package
set -e

echo "=== EMRI Step 1 Setup ==="

# Check for uv
if command -v uv &>/dev/null; then
    echo "Using uv..."
    uv venv .venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"
else
    echo "uv not found, falling back to pip..."
    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Activate environment:  source .venv/bin/activate"
echo "Run Streamlit UI:      streamlit run app/main.py"
echo "Run CLI:               emri --help"
echo "Run tests:             pytest"
echo "Launch Jupyter:        jupyter lab notebooks/"
