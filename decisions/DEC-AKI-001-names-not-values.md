# DEC-AKI-001 — inventory names and locations, never values

## Status

Accepted (2026-09-23).

## Context

An agent session inherits whatever its machine holds: environment variables, cloud profiles, git credentials, SSH keys, registry tokens, MCP server configs. Nobody granted that authority to the agent on purpose, and nobody checks whether it was used. The obvious way to list it would read the secrets and print them, which turns the audit tool into the leak.

## Decision

Each reader parses its file and keeps only the name of what it found (a profile, a host, a variable name, a key file name) plus where it was found. Values are tested for presence and discarded. The inventory is diffed against a usage log of grant ids; granted-but-unused is the finding, and `--max-unused` turns it into an exit code.

## Alternatives considered

- Hashing values to detect reuse across locations: useful, but a stored hash of a short token is guessable; deferred.
- Collecting usage by hooking the agent runtime: couples the tool to one runtime. v0.1 reads a JSONL log any runtime can write.

## Evidence

The fixtures plant six fake values across five locations; the no-leak test scans every output mode for them and asserts the fixtures really contain them.

## Rollback

The tool writes nothing; removing it removes the inventory, not any credential.
