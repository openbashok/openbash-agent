#!/usr/bin/env python3
"""
Shared Pentest Context MCP Server

Provides a shared knowledge base for all pentesting agents.
Agents can read and write findings, share intelligence (subdomains,
ports, services, technologies, credentials, URLs), and coordinate.

The context is stored in a JSON file that persists across agent calls.
All agents read/write the same file, enabling real-time collaboration.

Usage:
  Set PENTEST_CONTEXT_FILE env var to the path of the shared context file.
  Default: /tmp/pentest_context.json
"""

from mcp.server.fastmcp import FastMCP
import json
import os
import fcntl
from datetime import datetime
from pathlib import Path

mcp = FastMCP("context")

CONTEXT_FILE = os.environ.get("PENTEST_CONTEXT_FILE", "/tmp/pentest_context.json")


def _read_context():
    """Read the shared context file with file locking."""
    path = Path(CONTEXT_FILE)
    if not path.exists():
        return _default_context()
    try:
        with open(path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
            return data
    except (json.JSONDecodeError, IOError):
        return _default_context()


def _write_context(data):
    """Write the shared context file with file locking."""
    path = Path(CONTEXT_FILE)
    with open(path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(data, f, indent=2, ensure_ascii=False)
        fcntl.flock(f, fcntl.LOCK_UN)


def _default_context():
    return {
        "target": "",
        "scope": "",
        "started_at": "",
        "intel": {
            "subdomains": [],
            "ports": {},
            "services": {},
            "technologies": {},
            "credentials": [],
            "urls": [],
            "emails": [],
            "notes": [],
        },
        "findings": [],
        "agent_progress": {},
    }


# ── Intel sharing tools ──────────────────────────────────────────

@mcp.tool()
async def share_subdomains(subdomains: str) -> dict:
    """Share discovered subdomains with all agents. Pass comma-separated subdomains."""
    ctx = _read_context()
    new_subs = [s.strip() for s in subdomains.split(",") if s.strip()]
    existing = set(ctx["intel"]["subdomains"])
    added = [s for s in new_subs if s not in existing]
    ctx["intel"]["subdomains"].extend(added)
    _write_context(ctx)
    return {"added": len(added), "total": len(ctx["intel"]["subdomains"])}


@mcp.tool()
async def share_ports(host: str, ports: str) -> dict:
    """Share discovered open ports for a host. Ports as comma-separated: '22,80,443'."""
    ctx = _read_context()
    new_ports = [int(p.strip()) for p in ports.split(",") if p.strip().isdigit()]
    existing = set(ctx["intel"]["ports"].get(host, []))
    added = [p for p in new_ports if p not in existing]
    if host not in ctx["intel"]["ports"]:
        ctx["intel"]["ports"][host] = []
    ctx["intel"]["ports"][host].extend(added)
    ctx["intel"]["ports"][host] = sorted(set(ctx["intel"]["ports"][host]))
    _write_context(ctx)
    return {"host": host, "added": len(added), "total_ports": len(ctx["intel"]["ports"][host])}


@mcp.tool()
async def share_service(host: str, port: int, service: str, version: str = "") -> dict:
    """Share a discovered service. Example: share_service('10.0.0.1', 80, 'Apache', '2.4.41')."""
    ctx = _read_context()
    key = f"{host}:{port}"
    ctx["intel"]["services"][key] = {
        "service": service,
        "version": version,
        "discovered_at": datetime.now().isoformat(),
    }
    _write_context(ctx)
    return {"registered": key, "service": service, "version": version}


@mcp.tool()
async def share_technology(host: str, technology: str) -> dict:
    """Share a discovered technology on a host. Example: share_technology('example.com', 'WordPress 6.2')."""
    ctx = _read_context()
    if host not in ctx["intel"]["technologies"]:
        ctx["intel"]["technologies"][host] = []
    if technology not in ctx["intel"]["technologies"][host]:
        ctx["intel"]["technologies"][host].append(technology)
    _write_context(ctx)
    return {"host": host, "technologies": ctx["intel"]["technologies"][host]}


@mcp.tool()
async def share_credential(service: str, host: str, username: str, password: str, source: str = "") -> dict:
    """Share discovered credentials. Example: share_credential('ssh', '10.0.0.1', 'admin', 'admin123', 'hydra brute force')."""
    ctx = _read_context()
    cred = {
        "service": service,
        "host": host,
        "username": username,
        "password": password,
        "source": source,
        "discovered_at": datetime.now().isoformat(),
    }
    # Avoid duplicates
    for existing in ctx["intel"]["credentials"]:
        if (existing["service"] == service and existing["host"] == host and
                existing["username"] == username):
            return {"status": "already_exists"}
    ctx["intel"]["credentials"].append(cred)
    _write_context(ctx)
    return {"status": "added", "total_credentials": len(ctx["intel"]["credentials"])}


@mcp.tool()
async def share_urls(urls: str) -> dict:
    """Share discovered interesting URLs. Comma-separated."""
    ctx = _read_context()
    new_urls = [u.strip() for u in urls.split(",") if u.strip()]
    existing = set(ctx["intel"]["urls"])
    added = [u for u in new_urls if u not in existing]
    ctx["intel"]["urls"].extend(added)
    _write_context(ctx)
    return {"added": len(added), "total": len(ctx["intel"]["urls"])}


@mcp.tool()
async def share_emails(emails: str) -> dict:
    """Share discovered email addresses. Comma-separated."""
    ctx = _read_context()
    new_emails = [e.strip() for e in emails.split(",") if e.strip()]
    existing = set(ctx["intel"]["emails"])
    added = [e for e in new_emails if e not in existing]
    ctx["intel"]["emails"].extend(added)
    _write_context(ctx)
    return {"added": len(added), "total": len(ctx["intel"]["emails"])}


@mcp.tool()
async def add_note(agent: str, note: str) -> dict:
    """Add a free-form note to the shared context. Include your agent name."""
    ctx = _read_context()
    ctx["intel"]["notes"].append({
        "agent": agent,
        "note": note,
        "timestamp": datetime.now().isoformat(),
    })
    _write_context(ctx)
    return {"status": "noted", "total_notes": len(ctx["intel"]["notes"])}


# ── Findings tools ───────────────────────────────────────────────

@mcp.tool()
async def report_finding(
    title: str,
    description: str,
    impact: str,
    steps_to_reproduce: str,
    evidence: str,
    request: str,
    response: str,
    security_pillar: str,
    scope: str,
    remediation: str,
    severity: str,
    agent: str,
    screenshot: str = "",
) -> dict:
    """Report a vulnerability finding. steps_to_reproduce should be pipe-separated: 'Step 1|Step 2|Step 3'."""
    ctx = _read_context()
    finding_id = f"FINDING-{len(ctx['findings']) + 1:03d}"
    finding = {
        "id": finding_id,
        "title": title,
        "description": description,
        "impact": impact,
        "steps_to_reproduce": [s.strip() for s in steps_to_reproduce.split("|")],
        "evidence": evidence,
        "request": request,
        "response": response,
        "screenshot": screenshot,
        "security_pillar": security_pillar,
        "scope": scope,
        "remediation": remediation,
        "severity": severity.lower(),
        "agent": agent,
        "reported_at": datetime.now().isoformat(),
    }
    ctx["findings"].append(finding)
    _write_context(ctx)
    return {"status": "reported", "id": finding_id, "total_findings": len(ctx["findings"])}


# ── Read tools ───────────────────────────────────────────────────

@mcp.tool()
async def get_intel(category: str = "") -> dict:
    """Get shared intelligence. category: subdomains, ports, services, technologies, credentials, urls, emails, notes. Empty = all."""
    ctx = _read_context()
    if category and category in ctx["intel"]:
        return {category: ctx["intel"][category]}
    return ctx["intel"]


@mcp.tool()
async def get_findings(agent: str = "", severity: str = "") -> dict:
    """Get reported findings. Filter by agent (infra/web/osint) and/or severity (critical/high/medium/low/info)."""
    ctx = _read_context()
    findings = ctx["findings"]
    if agent:
        findings = [f for f in findings if f.get("agent") == agent]
    if severity:
        sevs = [s.strip().lower() for s in severity.split(",")]
        findings = [f for f in findings if f.get("severity") in sevs]
    return {"count": len(findings), "findings": findings}


@mcp.tool()
async def get_summary() -> dict:
    """Get a high-level summary of the entire pentest: target, findings count by severity, intel stats, agent progress."""
    ctx = _read_context()
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in ctx["findings"]:
        sev = f.get("severity", "info").lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    return {
        "target": ctx.get("target", ""),
        "scope": ctx.get("scope", ""),
        "findings": {
            "total": len(ctx["findings"]),
            "by_severity": severity_counts,
        },
        "intel": {
            "subdomains": len(ctx["intel"]["subdomains"]),
            "hosts_with_ports": len(ctx["intel"]["ports"]),
            "services": len(ctx["intel"]["services"]),
            "technologies": sum(len(v) for v in ctx["intel"]["technologies"].values()),
            "credentials": len(ctx["intel"]["credentials"]),
            "urls": len(ctx["intel"]["urls"]),
            "emails": len(ctx["intel"]["emails"]),
            "notes": len(ctx["intel"]["notes"]),
        },
        "agent_progress": ctx.get("agent_progress", {}),
    }


@mcp.tool()
async def get_target_info() -> dict:
    """Get the target and scope for this pentest."""
    ctx = _read_context()
    return {
        "target": ctx.get("target", ""),
        "scope": ctx.get("scope", ""),
        "started_at": ctx.get("started_at", ""),
    }


# ── Progress tracking ───────────────────────────────────────────

@mcp.tool()
async def update_progress(agent: str, iteration: int, status: str, summary: str = "") -> dict:
    """Update agent progress. status: running, completed, error. summary: what was done."""
    ctx = _read_context()
    if agent not in ctx["agent_progress"]:
        ctx["agent_progress"][agent] = []
    ctx["agent_progress"][agent].append({
        "iteration": iteration,
        "status": status,
        "summary": summary,
        "timestamp": datetime.now().isoformat(),
    })
    _write_context(ctx)
    return {"status": "updated"}


if __name__ == "__main__":
    mcp.run()
