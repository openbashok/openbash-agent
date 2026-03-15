# autopent

Automated penetration testing with AI agents. Runs multiple specialized Claude Code agents that collaborate through shared context to perform infrastructure, web application, and OSINT assessments.

Each agent shares intelligence in real-time: subdomains, ports, services, credentials, URLs. What one agent discovers, the others use immediately.

## How it works

```
Iteration 1 (recon):
  OSINT  → enumerates subdomains → shares: admin.target.com, dev.target.com
  INFRA  → scans ports          → shares: 22, 80, 443, 8080 open
  WEB    → detects technologies  → shares: WordPress 6.2, PHP 8.1

Iteration 2 (agents see each other's findings):
  OSINT  → "port 22 open, search for leaked SSH keys"
  INFRA  → "WordPress detected, run nuclei WP templates"
  WEB    → "admin.target.com found, fuzz directories"

Iteration 3-20 (deeper and deeper):
  All agents report_finding() when they find vulnerabilities
  All agents share credentials, URLs, notes between each other
```

## Installation

```bash
# 1. Install Claude Code (if not already)
curl -fsSL https://claude.ai/install.sh | bash

# 2. Install pentest-mcp (the tools)
git clone https://github.com/openbashok/pentest-mcp.git ~/pentest-mcp
cd ~/pentest-mcp && ./install.sh

# 3. Install autopent (the orchestrator)
git clone https://github.com/openbashok/autopent.git ~/autopent
cd ~/autopent && ./install.sh
```

## Usage

```bash
# Full pentest, all 3 agents, 20 iterations
autopent --target example.com

# Infrastructure only, 30 min max
autopent --target 192.168.1.0/24 --agents infra -T 30

# Web app deep testing, 50 iterations
autopent --target https://app.example.com --agents web -i 50 -B 10.0

# OSINT recon only
autopent --target example.com --agents osint -i 10 -T 5

# Full verbose to see everything
autopent --target example.com -v

# Quiet, just generate report
autopent --target example.com -q -o report.json
```

## Phased pentesting (maximum effectiveness)

Run in phases, each feeding the next with accumulated intel:

```bash
# Phase 1: OSINT (cheap, fast, gathers intel)
autopent --target example.com --agents osint -i 15 -T 10 -B 3.0 -o phase1.json

# Phase 2: Infrastructure (uses OSINT intel)
autopent --target example.com --agents infra -i 20 -T 30 -B 8.0 \
  --context-file phase1.context.json --no-plan -o phase2.json

# Phase 3: Web (uses everything found so far)
autopent --target example.com --agents web -i 30 -T 45 -B 15.0 \
  --context-file phase2.context.json --no-plan -o phase3.json
```

## Agents

| Agent | Focus | Tools used |
|---|---|---|
| `infra` | Network scanning, service detection, OS fingerprinting, CVE matching, default credentials | nmap, nuclei, nikto, hydra |
| `web` | OWASP Top 10, directory fuzzing, SQL injection, CMS scanning, auth testing | ffuf, sqlmap, wpscan, whatweb, nikto, httpx |
| `osint` | Subdomain enumeration, Google dorks, DNS analysis, technology fingerprinting, email harvesting | subfinder, httpx, whatweb, screensense |

## Parameters

| Flag | Default | Description |
|---|---|---|
| `--target` | (required) | IP, CIDR, domain, or URL |
| `--scope` | same as target | Scope definition for the agents |
| `-i, --iterations` | 20 | Conversational turns per agent |
| `-T, --time-limit` | 120 | Max execution time (minutes) |
| `-B, --budget` | 20.0 | Max estimated cost (USD) |
| `--agents` | infra,web,osint | Which agents to run |
| `-o, --output` | pentest_report.json | Output report path |
| `--context-file` | auto | Shared context file (for resuming) |
| `--agent-timeout` | 300 | Timeout per iteration (seconds) |
| `--no-plan` | false | Skip planning phase |
| `--no-monitor` | false | Skip final consolidation |
| `-v` | | Full verbose output |
| `-q` | | Quiet mode |

## Output

Two files are generated:

### pentest_report.json — Final report

```json
{
  "report": {
    "target": "example.com",
    "scope": "*.example.com",
    "date": "2026-03-15",
    "duration_minutes": 45,
    "total_cost_usd": 8.50,
    "summary": {
      "critical": 1,
      "high": 3,
      "medium": 5,
      "low": 2,
      "info": 8,
      "total": 19
    },
    "findings": [
      {
        "id": "FINDING-001",
        "title": "SQL Injection in login form",
        "description": "The login form at /api/auth is vulnerable to...",
        "impact": "Full database access, credential theft",
        "steps_to_reproduce": ["Step 1", "Step 2", "Step 3"],
        "evidence": "sqlmap confirmed boolean-based blind injection",
        "request": "POST /api/auth HTTP/1.1\n...",
        "response": "HTTP/1.1 200 OK\n...",
        "screenshot": "",
        "security_pillar": "Confidentiality",
        "scope": "https://app.example.com/api/auth",
        "remediation": "Use parameterized queries...",
        "severity": "critical",
        "agent": "web"
      }
    ]
  }
}
```

### pentest_report.context.json — Raw intelligence

Contains all shared intel: subdomains, ports, services, technologies, credentials, URLs, and notes from all agents across all iterations.

## Shared context MCP

The `context_mcp.py` server provides real-time collaboration between agents:

**Write tools** (agents share what they find):
- `share_subdomains()`, `share_ports()`, `share_service()`
- `share_technology()`, `share_credential()`, `share_urls()`
- `report_finding()`, `add_note()`

**Read tools** (agents see what others found):
- `get_intel()`, `get_findings()`, `get_summary()`

## Requirements

- Claude Code CLI with API key configured
- Python 3.9+
- [pentest-mcp](https://github.com/openbashok/pentest-mcp) for tool access (recommended)
- Pentesting tools installed (Kali Linux recommended)

## License

MIT
