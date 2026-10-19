# DEC-AKI-002: Inventory Codex MCP declarations

Date: 2026-10-18

An agent portfolio can share a machine while using different MCP configuration
formats. The JSON readers missed Codex's `.codex/config.toml` declarations.

Read home and explicitly supplied project configurations with the standard
library TOML reader. Record server names, inline and forwarded variable names,
bearer-token variable names, and HTTP header names. Never resolve environment
references, read OAuth stores, execute header helpers, or return header values.
A field that should name a variable but holds anything else is recorded as
`<invalid-name>`, because it may be the secret itself.
Keep disabled declarations visible because a scan describes configured authority;
the usage log remains the evidence that a particular grant was exercised.

The planted Codex fixture covers inline environment and header values. It is part
of the no-leak acceptance test. Malformed TOML is skipped as malformed MCP JSON is.
Layered configuration resolution and remote environment availability are outside
this inventory's claim.

Primary format reference, checked 2026-10-18:
[Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Amendment, 2026-10-19

Codex grant ids use their own namespace, `mcp:codex/<name>`, with the same
`/env/<VAR>` and `/header/<name>` suffixes. Sharing `mcp:server/<name>` with the
JSON readers gave a Codex server and a `.mcp.json` server of the same name one
grant id, so `diff` counted use of either as use of both. Ids from the JSON
readers are unchanged.
