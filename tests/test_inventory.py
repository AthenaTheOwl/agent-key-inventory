import json
import re
from pathlib import Path

from agent_key_inventory.cli import main
from agent_key_inventory.scan import scan

EX = Path(__file__).resolve().parents[1] / "examples"
HOME, ENV, PROJECT, USAGE = EX / "home", EX / "session.env-names", EX / "project", EX / "usage-2026-09.jsonl"
PLANTED = re.compile(r"PLANTED-SECRET-VALUE-\d+")
# A token format that is also a valid variable name; assembled at runtime, never a literal.
TOKEN_SHAPED = "gh" + "p_" + "PLANTEDSECRETVALUE" + "0" * 18


def _run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out + out.err


def _misplaced_codex_home(root):
    """Values typed where Codex expects env var names or an auth mode, and inline secrets
    in shapes the fixture does not use, assembled so no literal sits in the source."""
    value = "PLANTED-SECRET-VALUE-"
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("\n".join([
        "[mcp_servers.remote]",
        f'bearer_token_env_var = "{value}11"',
        f'env_vars = ["{value}12", {{ name = "Bearer {value}13" }}, "{TOKEN_SHAPED}"]',
        f'auth = "Bearer {value}17"',
        f'http_headers_helper = ["sh", "-c", "printf {value}18"]',
        f'oauth = {{ client_secret = "{value}19" }}',
        "[mcp_servers.remote.env_http_headers]",
        f'Authorization = "Bearer {value}14"',
        'X-Api-Key = "REMOTE_API_KEY"',
        "[mcp_servers.remote.env]",
        f'"{value}20" = "x"',
        "[mcp_servers.remote.http_headers]",
        f'"Bearer {value}21" = "x"',
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
        # the same Codex configs read as project configs
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(EX / "codex-home")],
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(EX / "codex-home"), "--json"],
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(misplaced)],
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(misplaced), "--json"],
    ):
        outputs.append(_run(argv, capsys)[1])
    # diff every --json inventory: the original home/project scan and each Codex scan.
    for scanned in outputs[1::2]:
        inventory.write_text(scanned, encoding="utf-8")
        outputs.append(_run(["diff", str(inventory), str(USAGE)], capsys)[1])
        outputs.append(_run(["diff", str(inventory), str(USAGE), "--json"], capsys)[1])
    for text in outputs:
        assert not PLANTED.search(text), text
        assert TOKEN_SHAPED not in text, text
    # The original fixture and Codex fixture hold ten distinct planted values.
    planted = {m for p in EX.rglob("*") if p.is_file() for m in PLANTED.findall(p.read_text(encoding="utf-8"))}
    assert len(planted) == 10
    assert len(set(PLANTED.findall((misplaced / ".codex" / "config.toml").read_text(encoding="utf-8")))) == 9


def test_codex_mcp_lists_inline_forwarded_and_http_authority():
    ids = {g["grant_id"] for g in scan(EX / "codex-home", {})}
    assert ids == {
        "mcp:codex/docs", "mcp:codex/docs/env/INLINE_TOKEN",
        "mcp:codex/docs/env/DOCS_TOKEN", "mcp:codex/docs/env/REMOTE_TOKEN",
        "mcp:codex/remote", "mcp:codex/remote/env/MCP_BEARER_TOKEN",
        "mcp:codex/remote/env/REMOTE_API_KEY", "mcp:codex/remote/header/Authorization",
        "mcp:codex/remote/auth/oauth", "mcp:codex/remote/oauth/client_secret",
        "mcp:codex/helper", "mcp:codex/helper/auth/chatgpt", "mcp:codex/helper/http_headers_helper",
    }


def test_codex_fields_that_name_a_variable_or_mode_never_echo_a_value(tmp_path):
    ids = {g["grant_id"] for g in scan(_misplaced_codex_home(tmp_path), {})}
    assert ids == {"mcp:codex/remote", "mcp:codex/remote/env/<invalid-name>",
                   "mcp:codex/remote/env/REMOTE_API_KEY", "mcp:codex/remote/auth/<invalid-mode>",
                   "mcp:codex/remote/http_headers_helper", "mcp:codex/remote/oauth/client_secret",
                   "mcp:codex/remote/header/<invalid-header>"}


def test_codex_project_config_is_included_and_malformed_config_is_skipped(tmp_path):
    project = tmp_path / "project"
    (project / ".codex").mkdir(parents=True)
    config = project / ".codex" / "config.toml"
    config.write_text('[mcp_servers.project]\ncommand = "example"\n', encoding="utf-8")
    grants = scan(tmp_path / "home", {}, project)
    assert grants == [{"grant_id": "mcp:codex/project", "kind": "mcp-server",
                       "source": "./.codex/config.toml", "name": "project"}]
    config.write_text("invalid toml [", encoding="utf-8")
    assert scan(tmp_path / "home", {}, project) == []


def test_codex_and_json_servers_with_one_name_stay_separate_grants(tmp_path, capsys):
    project = tmp_path / "project"
    (project / ".codex").mkdir(parents=True)
    (project / ".mcp.json").write_text('{"mcpServers": {"github": {"command": "gh-mcp"}}}', encoding="utf-8")
    (project / ".codex" / "config.toml").write_text('[mcp_servers.github]\ncommand = "gh-mcp"\n', encoding="utf-8")
    names, usage, inventory = tmp_path / "env-names", tmp_path / "usage.jsonl", tmp_path / "inventory.json"
    names.write_text("", encoding="utf-8")
    usage.write_text('{"grant": "mcp:server/github"}\n', encoding="utf-8")
    scanned = ["scan", "--home", str(tmp_path / "home"), "--env-names", str(names), "--cwd", str(project), "--json"]
    inventory.write_text(_run(scanned, capsys)[1], encoding="utf-8")
    code, out = _run(["diff", str(inventory), str(usage), "--json"], capsys)
    report = json.loads(out)
    assert (code, report["granted"]) == (1, 2)
    assert report["used"] == ["mcp:server/github"]
    assert report["unused"] == ["mcp:codex/github"]


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


# Identifier-shaped values: valid variable names that are nonetheless secrets. Assembled at
# runtime so no literal sits in the source; matched case-insensitively.
IDENT_PLANTED = re.compile(r"PLANTED_?SECRET_?VALUE_?\d+", re.IGNORECASE)
WITHHELD = re.compile(r"<withheld-name:[0-9a-f]{12}>")


def _identifier_shaped_home(root):
    """Name-shaped secrets in every field that should name a variable, beside real names."""
    v = "PLANTED" + "_SECRET_VALUE_"
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("\n".join([
        "[mcp_servers.remote]",
        f'bearer_token_env_var = "{v}20"',
        f'env_vars = ["{v}21", {{ name = "{v}22", source = "remote" }}, "{v.lower()}23", "DOCS_TOKEN"]',
        "[mcp_servers.remote.env_http_headers]",
        f'Authorization = "{v}24"',
        'X-Api-Key = "REMOTE_API_KEY"',
        'X-Region = "MCP_REGION"',
        "[mcp_servers.remote.env]",
        f'{v}25 = "x"',
        'INLINE_TOKEN = "x"',
        "[mcp_servers.other]",
        f'bearer_token_env_var = "{v}20"',
        "",
    ]), encoding="utf-8")
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"json": {"command": "x", "env": {
        f"{v}26": "x", "GITHUB_TOKEN": "x"}}}}), encoding="utf-8")
    return root


def test_identifier_shaped_values_in_name_fields_never_print(tmp_path, capsys):
    home = _identifier_shaped_home(tmp_path / "ident-home")
    names = tmp_path / "env-names"
    names.write_text("EDITOR\n", encoding="utf-8")
    inventory = tmp_path / "inventory.json"
    outputs = []
    for argv in (
        ["scan", "--home", str(home), "--env-names", str(names), "--cwd", str(home)],
        ["scan", "--home", str(home), "--env-names", str(names), "--cwd", str(home), "--json"],
        ["scan", "--home", str(HOME), "--env-names", str(names), "--cwd", str(home)],
        ["scan", "--home", str(HOME), "--env-names", str(names), "--cwd", str(home), "--json"],
    ):
        code, out = _run(argv, capsys)
        assert code == 0
        outputs.append(out)
    for scanned in outputs[1::2]:
        inventory.write_text(scanned, encoding="utf-8")
        outputs.append(_run(["diff", str(inventory), str(USAGE)], capsys)[1])
        outputs.append(_run(["diff", str(inventory), str(USAGE), "--json"], capsys)[1])
    for text in outputs:
        assert not IDENT_PLANTED.search(text), text
    # the fixture really holds the seven distinct planted values, in both spellings
    text = (home / ".codex" / "config.toml").read_text(encoding="utf-8") + (home / ".mcp.json").read_text()
    assert len({m.upper() for m in IDENT_PLANTED.findall(text)}) == 7


def test_identifier_shaped_values_get_a_stable_fingerprint(tmp_path):
    home = _identifier_shaped_home(tmp_path / "a")
    ids = {g["grant_id"] for g in scan(home, {"EDITOR": "set"}, home)}
    listed = {i for i in ids if "/env/" in i and not WITHHELD.search(i)}
    assert listed == {"mcp:codex/remote/env/DOCS_TOKEN", "mcp:codex/remote/env/REMOTE_API_KEY",
                      "mcp:codex/remote/env/INLINE_TOKEN", "mcp:server/json/env/GITHUB_TOKEN"}
    withheld = {WITHHELD.search(i).group() for i in ids if WITHHELD.search(i)}
    # planted 20 (in two servers), 21-26, and MCP_REGION, a name nothing confirms: eight labels
    assert len(withheld) == 8
    assert ({i.split("/env/")[1] for i in ids if i.startswith("mcp:codex/other/env/")}
            <= withheld)
    # the same value gets the same label in another server, another run and another directory
    again = {g["grant_id"] for g in scan(_identifier_shaped_home(tmp_path / "b"), {}, None)}
    assert {i for i in again if i.startswith("mcp:codex/")} == {i for i in ids if i.startswith("mcp:codex/")}
    other = [i for i in ids if i.startswith("mcp:codex/other/env/")]
    assert len(other) == 1 and other[0].replace("other", "remote", 1) in ids


def test_a_name_the_scanned_environment_defines_is_listed_as_written(tmp_path):
    home = _identifier_shaped_home(tmp_path)
    without = {g["grant_id"] for g in scan(home, {})}
    assert "mcp:codex/remote/env/MCP_REGION" not in without
    with_env = {g["grant_id"] for g in scan(home, {"MCP_REGION": "set"})}
    assert "mcp:codex/remote/env/MCP_REGION" in with_env
    assert len(with_env) == len(without)
