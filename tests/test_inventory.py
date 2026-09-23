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


def test_fixture_home_has_six_grants():
    from agent_key_inventory.scan import parse_env_file

    ids = [g["grant_id"] for g in scan(HOME, parse_env_file(ENV))]
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
    outputs = []
    for argv in (
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(PROJECT)],
        ["scan", "--home", str(HOME), "--env-names", str(ENV), "--cwd", str(PROJECT), "--json"],
    ):
        outputs.append(_run(argv, capsys)[1])
    inventory.write_text(outputs[-1], encoding="utf-8")
    outputs.append(_run(["diff", str(inventory), str(USAGE)], capsys)[1])
    outputs.append(_run(["diff", str(inventory), str(USAGE), "--json"], capsys)[1])
    for text in outputs:
        assert not PLANTED.search(text), text
    # and the fixture really does hold six planted values, so the check is not vacuous
    planted = {m for p in EX.rglob("*") if p.is_file() for m in PLANTED.findall(p.read_text(encoding="utf-8"))}
    assert len(planted) == 6


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
