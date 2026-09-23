# AGENTS.md — agent-key-inventory

Operating contract for AI agents working in this repo. Conventions match the rest of the AthenaTheOwl portfolio.

## What this repo is

A standard-library CLI that lists the credentials an agent session inherits from its machine (environment variable names, cloud profiles, git-host tokens, SSH private keys, package-registry tokens, container and cluster credentials, MCP servers and the env var names they receive) and diffs that inventory against a usage log.

## Rules

- Names and locations only. No reader may return, print, log or store a credential value. `tests/test_inventory.py::test_no_output_ever_contains_a_planted_value` is the contract; never weaken it.
- Fixture secrets are obviously fake (`PLANTED-SECRET-VALUE-NN`). Never add a value shaped like a real provider token.
- A new source needs a planted fixture and a line in the no-leak test.
- Record design choices in `decisions/DEC-AKI-NNN-*.md`.

## Run

    python -m pip install -e . pytest
    python -m pytest -q
