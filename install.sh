#!/bin/bash
# autopent installer
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== autopent installer ==="
echo ""

# Check claude is installed
if command -v claude &>/dev/null; then
    echo "  ✓ claude code"
else
    echo "  ✗ claude code (required — install from https://claude.ai/install.sh)"
    exit 1
fi

# Check pentest-mcp is installed
if [ -f "$HOME/pentest-mcp/claude_mcp_config.json" ]; then
    echo "  ✓ pentest-mcp ($HOME/pentest-mcp)"
elif [ -f "$SCRIPT_DIR/../pentest-mcp/claude_mcp_config.json" ]; then
    echo "  ✓ pentest-mcp ($SCRIPT_DIR/../pentest-mcp)"
else
    echo "  ✗ pentest-mcp (recommended — git clone https://github.com/openbashok/pentest-mcp.git ~/pentest-mcp && cd ~/pentest-mcp && ./install.sh)"
    echo "    autopent works without it but agents won't have MCP tools"
fi

# Create venv for context server
echo ""
echo "Setting up Python environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "  ✓ Python dependencies installed"

# Create wrapper
mkdir -p "$HOME/bin"
cat > "$HOME/bin/autopent" << EOF
#!/bin/bash
$VENV_DIR/bin/python $SCRIPT_DIR/pentest.py "\$@"
EOF
chmod +x "$HOME/bin/autopent"
echo "  ✓ Wrapper installed: ~/bin/autopent"

# Add to PATH if needed
if ! echo "$PATH" | grep -q "$HOME/bin"; then
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile"; do
        if [ -f "$rc" ]; then
            echo 'export PATH="$HOME/bin:$PATH"' >> "$rc"
        fi
    done
    echo '  ✓ Added ~/bin to PATH (restart shell or source ~/.bashrc)'
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Usage:"
echo "  autopent --target example.com"
echo "  autopent --target 192.168.1.0/24 --agents infra -T 30"
echo "  autopent --target https://app.example.com --agents web -i 30 -B 10.0"
echo ""
echo "Run 'autopent --help' for all options."
