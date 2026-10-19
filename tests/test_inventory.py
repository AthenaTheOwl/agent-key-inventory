import json
import re
from pathlib import Path

from agent_key_inventory.cli import main
from agent_key_inventory.scan import scan

EX = Path(__file__).resolve().parents[1] / "examples"
HOME, ENV, PROJECT, USAGE = EX / "home", EX / "session.env-names", EX / "project", EX / "usage-2026-09.jsonl"
PLANTED = re.compile(r"PLANTED-SECRET-VALUE-\d+")


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out + out.err


def _misplaced_codex_home(root):
    """Values typed where Codex expects env var names, assembled so no literal sits in the source."""
    value = "PLANTED-SECRET-VALUE-"
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("\n".join([
        "[mcp_servers.remote]",
        f'bearer_token_env_var = "{value}11"',
        f'env_vars = ["{value}12", {{ name = "Bearer {value}13" }}]',
        "[mcp_servers.remote.env_http_headers]",
        f'Authorization = "Bearer {value}14"',
        'X-Api-Key = "REMOTE_API_KEY"',
        "",
    ]), encoding="utf-8")
    return root


def test_fixture_home_has_six_grants():
    from agent_key_inventory.scan import parse_env_names

    ids = [g["grant_id"] for g in scan(HOME, parse_env_names(ENV))]
    assert ids == [
        "aws:profile/default",
        "env:ANTHROPIC_API_KEY",
        "env:GITHUB_TOKEN",
        "gh:host/github.com",
        "npm:registry/registry.npmjs.org",
        "ssh:key/id_ed25519",
    ]


def test_diff_reports_four_unused_and_exits_1(tmp_path, capsys):
    inventory = tmp_path / "inventory.json"
    code, out = _run(["scan", "--home", str(HOME), "--env-names", str(ENV), "--json"], capsys)
    assert code == 0
    inventory.write_text(out, encoding="utf-8")
    code, out = _run(["diff", str(inventory), str(USAGE), "--json"], capsys)
    report = json.loads(out)
    assert code == 1
    assert report["used"] == ["env:ANTHROPIC_API_KEY", "gh:host/github.com"]
    assert len(report["unused"]) == 4
    assert _run(["diff", str(inventory), str(USAGE), "--max-unused", "4"], capsys)[0] == 0


def test_mcp_servers_and_their_env_names_are_listed():
    ids = [g["grant_id"] for g in scan(HOME, {}, PROJECT)]
    assert "mcp:server/github" in ids
    assert "mcp:server/github/env/GITHUB_PERSONAL_ACCESS_TOKEN" in ids


def test_no_output_ever_contains_a_planted_value(tmp_path, capsys):
    inventory = tmp_path / "inventory.json"
    misplaced = _misplaced_codex_home(tmp_path / "misplaced-home")
    outputs = []
    for argv in (
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(PROJECT)],
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(PROJECT), "--json"],
        ["scan", "--home", str(EX / "codex-home"), "--env-names", str(ENV)],
        ["scan", "--home", str(EX / "codex-home"), "--env-names", str(ENV), "--json"],
        ["scan", "--home", str(misplaced), "--env-names", str(ENV)],
        ["scan", "--home", str(misplaced), "--env-names", str(ENV), "--json"],
    ):
        outputs.append(_run(argv, capsys)[1])
    # diff every --json inventory: the original home/project scan and both Codex scans.
    for scanned in (outputs[1], outputs[3], outputs[5]):
        inventory.write_text(scanned, encoding="utf-8")
        outputs.append(_run(["diff", str(inventory), str(USAGE)], capsys)[1])
        outputs.append(_run(["diff", str(inventory), str(USAGE), "--json"], capsys)[1])
    for text in outputs:
        assert not PLANTED.search(text), text
    # The original fixture and Codex fixture hold eight distinct planted values.
    planted = {m for p in EX.rglob("*") if p.is_file() for m in PLANTED.findall(p.read_text(encoding="utf-8"))}
    assert len(planted) == 8


def test_codex_mcp_lists_inline_forwarded_and_http_authority():
    ids = {g["grant_id"] for g in scan(EX / "codex-home", {})}
    assert ids == {
        "mcp:server/docs", "mcp:server/docs/env/INLINE_TOKEN",
        "mcp:server/docs/env/DOCS_TOKEN", "mcp:server/docs/env/REMOTE_TOKEN",
        "mcp:server/remote", "mcp:server/remote/env/MCP_BEARER_TOKEN",
        "mcp:server/remote/env/REMOTE_API_KEY", "mcp:server/remote/header/Authorization",
    }


def test_codex_fields_that_name_a_variable_never_echo_a_value(tmp_path):
    ids = {g["grant_id"] for g in scan(_misplaced_codex_home(tmp_path), {})}
    assert ids == {"mcp:server/remote", "mcp:server/remote/env/<invalid-name>",
                   "mcp:server/remote/env/REMOTE_API_KEY"}


def test_codex_project_config_is_included_and_malformed_config_is_skipped(tmp_path):
    project = tmp_path / "project"
    (project / ".codex").mkdir(parents=True)
    config = project / ".codex" / "config.toml"
    config.write_text('[mcp_servers.project]\ncommand = "example"\n', encoding="utf-8")
    grants = scan(tmp_path / "home", {}, project)
    assert grants == [{"grant_id": "mcp:server/project", "kind": "mcp-server",
                       "source": "./.codex/config.toml", "name": "project"}]
    config.write_text("invalid toml [", encoding="utf-8")
    assert scan(tmp_path / "home", {}, project) == []


def test_codex_home_config_is_read_once_when_cwd_is_home_spelled_differently(tmp_path, monkeypatch):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text('[mcp_servers.project]\ncommand = "example"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert [g["source"] for g in scan(tmp_path, {}, Path("."))] == ["~/.codex/config.toml"]


def test_bad_usage_log_exits_2(tmp_path, capsys):
    bad = tmp_path / "usage.jsonl"
    bad.write_text("not json\n", encoding="utf-8")
    inventory = tmp_path / "inventory.json"
    inventory.write_text('{"grants": []}', encoding="utf-8")
    assert _run(["diff", str(inventory), str(bad)], capsys)[0] == 2


def test_env_values_are_dropped():
    # values assembled at runtime so no literal assignment sits in the source
    names = ["ANTHROPIC" + "_API_KEY", "DB" + "_PASSWORD", "EDITOR", "EMPTY" + "_TOKEN"]
    env = {n: "PLANTED-SECRET-VALUE-" + str(90 + i) for i, n in enumerate(names)}
    env[names[3]] = ""
    grants = scan(Path("/nonexistent-home"), env)
    assert [g["name"] for g in grants] == [names[0], names[1]]
    assert not PLANTED.search(json.dumps(grants))


def test_pem_header_marks_a_private_key_without_a_pub(tmp_path):
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    header = "-----BEGIN " + "OPENSSH " + "PRIVATE KEY-----"
    (ssh / "deploy_key").write_text("\n".join([header, "PLANTED-SECRET-VALUE-99", ""]), encoding="utf-8")
    (ssh / "notes.txt").write_text("not a key", encoding="utf-8")
    grants = scan(tmp_path, {})
    assert [g["grant_id"] for g in grants] == ["ssh:key/deploy_key"]
