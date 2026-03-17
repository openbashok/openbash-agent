#!/bin/bash
# openbash installer
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Parse arguments ──────────────────────────────────────────────
GLOBAL_INSTALL=false
for arg in "$@"; do
    case "$arg" in
        --global) GLOBAL_INSTALL=true ;;
        --help|-h)
            echo "Usage: ./install.sh [--global]"
            echo ""
            echo "  --global   Install system-wide in /opt/openbash-agent (requires root)"
            echo "             Without --global, installs for current user only"
            exit 0
            ;;
    esac
done

# ── Global install ───────────────────────────────────────────────
if [ "$GLOBAL_INSTALL" = true ]; then
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: --global requires root. Run with: sudo ./install.sh --global"
        exit 1
    fi

    INSTALL_DIR="/opt/openbash-agent"
    VENV_DIR="$INSTALL_DIR/.venv"

    echo "=== openbash global installer ==="
    echo ""
    echo "  Install dir: $INSTALL_DIR"
    echo ""

    # Copy files to /opt (or update if already there)
    if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR"
        cp -r "$SCRIPT_DIR/pentest.py" "$INSTALL_DIR/"
        cp -r "$SCRIPT_DIR/providers.py" "$INSTALL_DIR/"
        cp -r "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
        [ -d "$SCRIPT_DIR/prompts" ] && cp -r "$SCRIPT_DIR/prompts" "$INSTALL_DIR/"
        [ -f "$SCRIPT_DIR/rules.md" ] && cp "$SCRIPT_DIR/rules.md" "$INSTALL_DIR/"
        echo "  ✓ Files copied to $INSTALL_DIR"
    else
        echo "  ✓ Already running from $INSTALL_DIR"
    fi

    # Create venv and install dependencies
    echo ""
    echo "Setting up Python environment..."
    python3 -m venv "$VENV_DIR" 2>/dev/null || python3.7 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
    echo "  ✓ Python dependencies installed (anthropic, mcp, psutil)"

    # Generate rules.md
    echo ""
    echo "Generating rules.md..."
    cat > "$INSTALL_DIR/rules.md" << RULES
# Global Agent Rules

## Environment
- OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '"' || echo "Unknown")

## Paths
- Nuclei templates: $(find /root /home -maxdepth 3 -name "nuclei-templates" -type d 2>/dev/null | head -1 || echo "NOT FOUND")
- Wordlists: $(ls -d /usr/share/wordlists 2>/dev/null || echo "NOT FOUND")
- Seclists: $(ls -d /usr/share/seclists 2>/dev/null || ls -d /usr/share/wordlists/seclists 2>/dev/null || echo "NOT FOUND")
- Nmap scripts: $(ls -d /usr/share/nmap/scripts 2>/dev/null || echo "NOT FOUND")

## Tool rules
- nuclei: use \`nuclei -u URL -silent\` without -t flag (uses default templates automatically)
- nmap: ALWAYS use -Pn flag (hosts often block ping probes)
- ffuf/gobuster: use wordlists from /usr/share/wordlists/
- hydra: use wordlists from /usr/share/wordlists/
RULES
    echo "  ✓ rules.md generated"

    # Create global wrapper
    cat > /usr/local/bin/openbash << EOF
#!/bin/bash
exec $VENV_DIR/bin/python $INSTALL_DIR/pentest.py "\$@"
EOF
    chmod +x /usr/local/bin/openbash
    echo "  ✓ Wrapper installed: /usr/local/bin/openbash"

    # Create /etc/openbash/ config directory and copy models + config
    mkdir -p /etc/openbash

    # Always update models.json (new models may have been added)
    cp "$SCRIPT_DIR/models.json" /etc/openbash/models.json 2>/dev/null || \
        cp "$INSTALL_DIR/models.json" /etc/openbash/models.json 2>/dev/null || true
    if [ -f /etc/openbash/models.json ]; then
        chmod 644 /etc/openbash/models.json
        echo "  ✓ Models registry: /etc/openbash/models.json"
    fi
    if [ ! -f /etc/openbash/openbash.conf ]; then
        cat > /etc/openbash/openbash.conf << 'CONF'
# ┌──────────────────────────────────────────────────────────────────┐
# │  /etc/openbash/openbash.conf — system-wide openbash config      │
# │                                                                  │
# │  Priority: CLI flags > env vars > ~/.openbash.conf > this file   │
# │  Users can override any setting in ~/.openbash.conf              │
# └──────────────────────────────────────────────────────────────────┘

# ── API Keys ─────────────────────────────────────────────────────
# Set the key for the provider you want to use.
# Only the key for your chosen provider is required.
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
XAI_API_KEY=

# ── Model Preset ────────────────────────────────────────────────
# A preset selects which model to use for each role (agent, planner, etc.)
# Available presets (defined in /etc/openbash/models.json):
#   default       — Claude Sonnet 4 (Anthropic)
#   cheap         — Claude Haiku (Anthropic, cheapest)
#   best          — Claude Sonnet 4.6 (Anthropic, best)
#   openai        — GPT-4o (OpenAI)
#   openai-cheap  — GPT-4.1-mini (OpenAI, cheap)
#   grok          — Grok 3 (xAI)
#   gemini        — Gemini 2.5 Pro (Google)
#   gemini-cheap  — Gemini 2.5 Flash (Google, cheap)
# To add custom presets or new models, edit /etc/openbash/models.json
PRESET=default

# ── Model Overrides ──────────────────────────────────────────────
# Override the model for ALL roles (ignores preset):
# MODEL=gpt-4o
#
# Override individual roles (takes priority over MODEL and PRESET):
# AGENT_MODEL=claude-sonnet-4-6
# PLANNER_MODEL=gpt-4o-mini
# ANALYST_MODEL=gemini-2.5-pro
# CURATOR_MODEL=claude-haiku-4-5-20251001
# MONITOR_MODEL=grok-3

# ── Execution Limits ─────────────────────────────────────────────
# Max conversation turns per agent
ITERATIONS=20

# Max total execution time in minutes
TIME_LIMIT=120

# Max estimated cost in USD (stops agents when exceeded)
BUDGET=20.0

# Timeout per individual agent in seconds
AGENT_TIMEOUT=600

# Number of plan-execute-review rounds
ROUNDS=1

# ── Agent Configuration ──────────────────────────────────────────
# Which agents to run (comma-separated: infra, web, osint)
AGENTS=infra,web,osint

# Output report path
OUTPUT=pentest_report.json
CONF
        chmod 640 /etc/openbash/openbash.conf
        echo "  ✓ Config created: /etc/openbash/openbash.conf"
    else
        echo "  ✓ Config exists: /etc/openbash/openbash.conf (not overwritten)"
    fi

    # Set permissions: readable/executable by all, writable by root
    chmod -R 755 "$INSTALL_DIR"

    echo ""
    echo "=== Global installation complete ==="
    echo ""
    echo "1. Edit the API key in /etc/openbash/openbash.conf:"
    echo "   nano /etc/openbash/openbash.conf"
    echo ""
    echo "2. All users can now run:"
    echo "   openbash --target example.com"
    echo ""
    echo "Users can override settings in ~/.openbash.conf"
    echo ""
    echo "To update: cd $INSTALL_DIR && git pull && ./install.sh --global"
    exit 0
fi

# ── Local install (per-user, original behavior) ─────────────────
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
python3 -m venv "$VENV_DIR" 2>/dev/null || python3.7 -m venv "$VENV_DIR"
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
