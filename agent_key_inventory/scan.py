"""Enumerate the ambient authority an agent session inherits. Names and locations only.

Every reader below parses a file that may hold live secrets and keeps only the
name of what it found: a profile, a host, a variable name, a key file name.
No function returns, logs or stores a value. That is the contract the tests pin.
"""

from __future__ import annotations

import configparser
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

ENV_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|_PAT$|SESSION)", re.IGNORECASE)
VAR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INVALID_VAR = "<invalid-name>"


@dataclass(frozen=True, order=True)
class Grant:
    grant_id: str  # stable id used in usage logs, e.g. "env:OPENAI_API_KEY"
    kind: str
    source: str    # where it was found, relative to the scanned home or cwd
    name: str


def _rel(path: Path, root: Path) -> str:
    try:
        return "~/" + path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def from_env(env: dict[str, str]) -> list[Grant]:
    return [Grant(f"env:{k}", "env-var", "environment", k) for k in sorted(env) if ENV_NAME.search(k) and env[k]]


def parse_env_names(path: Path) -> dict[str, str]:
    """One variable name per line: the shape of an environment without its values."""
    names = [l.strip() for l in path.read_text(encoding="utf-8").splitlines()]
    return {n: "set" for n in names if n and not n.startswith("#")}


def parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines (like a .env file). Values are only tested for emptiness by callers."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().removeprefix("export ").strip()] = v.strip()
    return out


def from_aws(home: Path) -> list[Grant]:
    path = home / ".aws" / "credentials"
    if not path.is_file():
        return []
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    return [Grant(f"aws:profile/{s}", "cloud-profile", _rel(path, home), s)
            for s in cfg.sections() if cfg.has_option(s, "aws_access_key_id")]


def from_gh(home: Path) -> list[Grant]:
    path = home / ".config" / "gh" / "hosts.yml"
    if not path.is_file():
        return []
    grants, host = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
            host = line.rstrip()[:-1].strip()
        elif host and re.match(r"\s+oauth_token\s*:", line):
            grants.append(Grant(f"gh:host/{host}", "git-host-token", _rel(path, home), host))
    return grants


def from_ssh(home: Path) -> list[Grant]:
    d = home / ".ssh"
    if not d.is_dir():
        return []
    grants = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix == ".pub" or f.name in {"known_hosts", "config", "authorized_keys"}:
            continue
        first = f.read_text(encoding="utf-8", errors="ignore").lstrip()[:80]
        pem_private = first.startswith("-----BEGIN") and "PRIVATE" in first.splitlines()[0]
        if pem_private or f.with_name(f.name + ".pub").is_file():
            grants.append(Grant(f"ssh:key/{f.name}", "ssh-private-key", _rel(f, home), f.name))
    return grants


def from_token_files(home: Path) -> list[Grant]:
    grants = []
    npmrc = home / ".npmrc"
    if npmrc.is_file():
        for line in npmrc.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*//([^/:]+)[^:]*:_authToken\s*=", line)
            if m:
                grants.append(Grant(f"npm:registry/{m.group(1)}", "package-registry-token", "~/.npmrc", m.group(1)))
    pypirc = home / ".pypirc"
    if pypirc.is_file():
        cfg = configparser.ConfigParser()
        cfg.read(pypirc, encoding="utf-8")
        grants += [Grant(f"pypi:index/{s}", "package-registry-token", "~/.pypirc", s)
                   for s in cfg.sections() if cfg.has_option(s, "password")]
    netrc = home / ".netrc"
    if netrc.is_file():
        for m in re.finditer(r"\bmachine\s+(\S+)", netrc.read_text(encoding="utf-8")):
            grants.append(Grant(f"netrc:machine/{m.group(1)}", "netrc-login", "~/.netrc", m.group(1)))
    docker = home / ".docker" / "config.json"
    if docker.is_file():
        auths = json.loads(docker.read_text(encoding="utf-8")).get("auths", {})
        grants += [Grant(f"docker:registry/{h}", "container-registry-auth", "~/.docker/config.json", h)
                   for h, v in sorted(auths.items()) if isinstance(v, dict) and v.get("auth")]
    kube = home / ".kube" / "config"
    if kube.is_file():
        text = kube.read_text(encoding="utf-8")
        users = re.search(r"^users:\s*\n((?:[ \t-].*\n?)*)", text, re.MULTILINE)
        for m in re.finditer(r"-\s*name:\s*(\S+)", users.group(1) if users else ""):
            grants.append(Grant(f"kube:user/{m.group(1)}", "cluster-credential", "~/.kube/config", m.group(1)))
    return grants


MCP_FILES = [".mcp.json", ".cursor/mcp.json", ".claude.json", ".claude/settings.json",
             "AppData/Roaming/Claude/claude_desktop_config.json",
             "Library/Application Support/Claude/claude_desktop_config.json"]


def from_mcp(home: Path, cwd: Path | None) -> list[Grant]:
    """MCP servers an agent can call, and the env var names each one is handed."""
    grants = []
    candidates = [(home / f, home) for f in MCP_FILES] + ([(cwd / ".mcp.json", cwd)] if cwd else [])
    for path, root in candidates:
        if not path.is_file():
            continue
        try:
            servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
        except ValueError:
            continue
        where = _rel(path, root) if root == home else "./" + path.relative_to(root).as_posix()
        for name, spec in sorted(servers.items()):
            grants.append(Grant(f"mcp:server/{name}", "mcp-server", where, name))
            for var in sorted((spec or {}).get("env", {}) or {}):
                grants.append(Grant(f"mcp:server/{name}/env/{var}", "mcp-server-env", where, var))
    return grants


def _var_name(value: object) -> str | None:
    """A config value that should name an env var. Anything else may be the secret itself."""
    if not isinstance(value, str) or not value:
        return None
    return value if VAR_NAME.fullmatch(value) else INVALID_VAR


def from_codex_mcp(home: Path, cwd: Path | None) -> list[Grant]:
    """Inventory Codex MCP declarations without resolving or returning credentials.

    OAuth stores and header helper commands are deliberately never read or run.
    Disabled servers remain visible: this is configured authority, not a claim
    that a particular session loaded or used the server.
    """
    grants = []
    candidates = [(home / ".codex" / "config.toml", home)]
    if cwd is not None and cwd != home:
        candidates.append((cwd / ".codex" / "config.toml", cwd))
    for path, root in candidates:
        if not path.is_file():
            continue
        try:
            config = tomllib.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            continue
        servers = config.get("mcp_servers", {})
        if not isinstance(servers, dict):
            continue
        where = _rel(path, home) if root == home else "./.codex/config.toml"
        for name, spec in sorted(servers.items()):
            if not isinstance(spec, dict):
                continue
            grants.append(Grant(f"mcp:server/{name}", "mcp-server", where, name))
            env = spec.get("env", {})
            variables = set(env) if isinstance(env, dict) else set()
            forwarded = spec.get("env_vars", [])
            if isinstance(forwarded, list):
                for item in forwarded:
                    var = _var_name(item.get("name") if isinstance(item, dict) else item)
                    if var:
                        variables.add(var)
            bearer = _var_name(spec.get("bearer_token_env_var"))
            if bearer:
                variables.add(bearer)
            headers = spec.get("env_http_headers", {})
            if isinstance(headers, dict):
                variables.update(var for var in map(_var_name, headers.values()) if var)
            for var in sorted(variables):
                grants.append(Grant(f"mcp:server/{name}/env/{var}", "mcp-server-env", where, var))
            # Header *names* identify configured inline authority; values never escape.
            static_headers = spec.get("http_headers", {})
            if isinstance(static_headers, dict):
                for header in sorted(static_headers):
                    grants.append(Grant(f"mcp:server/{name}/header/{header}", "mcp-server-header", where, header))
    return grants


def scan(home: Path, env: dict[str, str], cwd: Path | None = None) -> list[dict]:
    grants = (from_env(env) + from_aws(home) + from_gh(home) + from_ssh(home)
              + from_token_files(home) + from_mcp(home, cwd) + from_codex_mcp(home, cwd))
    return [asdict(g) for g in sorted(set(grants))]
