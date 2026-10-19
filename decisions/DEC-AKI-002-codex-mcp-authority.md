# DEC-AKI-002: Inventory Codex MCP declarations

Date: 2026-10-18

An agent portfolio can share a machine while using different MCP configuration
formats. The JSON readers missed Codex's `.codex/config.toml` declarations.

Read home and explicitly supplied project configurations with the standard
library TOML reader. Record server names, inline and forwarded variable names,
bearer-token variable names, and HTTP header names. Never resolve environment
references, read OAuth stores, execute header helpers, or return header values.
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

Three more settings carry authority and are recorded by presence only: an inline
`oauth.client_secret`, which Codex saves in `config.toml` (kind
`mcp-server-inline-secret`); the `auth` mode, `oauth` or `chatgpt` (the current
ChatGPT session), with any other value recorded as `<invalid-mode>`, recorded only
when `auth` is set explicitly, so the implicit default `oauth` is not assumed; and an
`http_headers_helper` command. The secret and the command are never returned, and
the helper is never run. The planted Codex fixture now also holds values in a
client secret and a helper command.

A field that should name a variable (an inline `env` key, an `env_vars` entry,
`bearer_token_env_var` or an `env_http_headers` value) but holds anything else, or
holds a known token format that is also a valid name (GitHub `ghp_`/`github_pat_`,
AWS `AKIA`/`ASIA`, Stripe `sk_live_` and similar), is recorded as `<invalid-name>`,
because it may be the secret itself. A static `http_headers` name that is not an
HTTP token is recorded as `<invalid-header>`. A secret shaped like an ordinary
variable name cannot be told apart from one and is recorded as written; the guard
narrows that risk without closing it.

To be exact about the original list: the variable names recorded are inline `env`
keys, `env_vars` entries, `bearer_token_env_var`, and the variables that
`env_http_headers` reads header values from. The header names recorded are the
static `http_headers` names; `env_http_headers` header names are not recorded.
Only `<home>/.codex/config.toml` is read at home; `$CODEX_HOME` is not followed.

Configuration reference checked 2026-10-19:
[Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
