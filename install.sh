#!/bin/bash
# openbash installer
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== openbash installer ==="
echo ""

# Check ANTHROPIC_API_KEY
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "  ✓ ANTHROPIC_API_KEY set"
else
    echo "  ⚠ ANTHROPIC_API_KEY not set — export it before running openbash"
fi

# Create venv and install dependencies
echo ""
echo "Setting up Python environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "  ✓ Python dependencies installed (anthropic, mcp, psutil)"

# Generate rules.md — environment profile for all agents
echo ""
echo "Generating rules.md..."
cat > "$SCRIPT_DIR/rules.md" << RULES
# Global Agent Rules

## Environment
- User: $(whoami)
- Home: $HOME
- OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"' || echo "Unknown")

## Paths
- Nuclei templates: $(find $HOME -maxdepth 2 -name "nuclei-templates" -type d 2>/dev/null | head -1 || echo "NOT FOUND")
- Wordlists: $(ls -d /usr/share/wordlists 2>/dev/null || echo "NOT FOUND")
- Seclists: $(ls -d /usr/share/seclists 2>/dev/null || ls -d /usr/share/wordlists/seclists 2>/dev/null || echo "NOT FOUND")
- Nmap scripts: $(ls -d /usr/share/nmap/scripts 2>/dev/null || echo "NOT FOUND")

## Tool rules
- nuclei: use \`nuclei -u URL -silent\` without -t flag (uses default templates automatically)
- nmap: ALWAYS use -Pn flag (hosts often block ping probes)
- ffuf/gobuster: use wordlists from /usr/share/wordlists/
- hydra: use wordlists from /usr/share/wordlists/
- NEVER reference /root/ paths — you are NOT root
- NEVER use sudo — run everything as current user
RULES
echo "  ✓ rules.md generated"

# Create wrapper
mkdir -p "$HOME/bin"
cat > "$HOME/bin/openbash" << EOF
#!/bin/bash
$VENV_DIR/bin/python $SCRIPT_DIR/pentest.py "\$@"
EOF
chmod +x "$HOME/bin/openbash"
echo "  ✓ Wrapper installed: ~/bin/openbash"

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
echo "  export ANTHROPIC_API_KEY=sk-ant-..."
echo "  openbash --target example.com"
echo "  openbash --target 192.168.1.0/24 --agents infra -T 30"
echo "  openbash --target https://app.example.com --agents web -i 30 -B 10.0"
echo ""
echo "Run 'openbash --help' for all options."
