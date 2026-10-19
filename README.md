# agent-key-inventory

An agent session starts with whatever its machine holds: an API key in the environment, a cloud profile, a GitHub token, an SSH key, a registry token, a handful of MCP servers each handed its own token. Nobody granted that authority to the agent. It was ambient. This tool lists it, then asks which of it was used.

## What it does

`scan` walks a home directory (and optionally a project directory) and lists every credential an agent run there would inherit, by **name and location only**. It never prints, logs or stores a value.

Sources in v0.1: environment variable names that look like credentials, `~/.aws/credentials` profiles with keys, `gh` host tokens, SSH private keys, `.npmrc` / `.pypirc` / `.netrc` entries, Docker registry auths, kube users, and MCP servers in the usual config files together with the env var names each server receives.

`diff` compares that inventory with a usage log, one JSON object per use: `{"grant": "env:ANTHROPIC_API_KEY"}`. Authority that was granted and never used is the finding. Run it monthly and the unused list is what to revoke.

## Try it

```bash
python -m pip install -e .
agent-key-inventory scan --home examples/home --env-names examples/session.env-names
```

```text
6 grant(s) an agent run here would inherit
  cloud-profile            aws:profile/default                              ~/.aws/credentials
  env-var                  env:ANTHROPIC_API_KEY                            environment
  env-var                  env:GITHUB_TOKEN                                 environment
  git-host-token           gh:host/github.com                               ~/.config/gh/hosts.yml
  package-registry-token   npm:registry/registry.npmjs.org                  ~/.npmrc
  ssh-private-key          ssh:key/id_ed25519                               ~/.ssh/id_ed25519
```

```bash
agent-key-inventory scan --home examples/home --env-names examples/session.env-names --json > inventory.json
agent-key-inventory diff inventory.json examples/usage-2026-09.jsonl
```

```text
granted 6, used 2, unused 4
  unused  cloud-profile            aws:profile/default
  unused  env-var                  env:GITHUB_TOKEN
  unused  package-registry-token   npm:registry/registry.npmjs.org
  unused  ssh-private-key          ssh:key/id_ed25519
```

Exit 1, because four grants went unused and the default `--max-unused` is 0. Exit 2 means bad input.

The example home and project hold six planted values; the separate Codex fixture adds four. All are `PLANTED-SECRET-VALUE-NN`. The test suite runs output modes and fails if any of them appears.

Without `--home` and `--env-file` it scans your own home directory and this process's environment. Output stays names and locations, but it is still a map of what your machine can reach, so treat it accordingly.

### Codex MCP configuration

Home and explicitly supplied project `.codex/config.toml` files are also inventoried.
At home only `<home>/.codex/config.toml` is read; `$CODEX_HOME` is not followed.
The scan includes inline, forwarded, bearer-token and header-sourcing
(`env_http_headers`) variable names, and static `http_headers` names. Header values
stay private. A field that should name a variable but holds anything else, or holds
a known token format such as a GitHub, AWS or Stripe key, is listed as
`<invalid-name>`, since it may be the secret itself; a header name that is not a
valid HTTP token is listed as `<invalid-header>`. A value shaped like an ordinary
variable name is listed as written only when it is clearly a name: the scanned
environment defines it, or it is upper case and ends in a credential word such as
`_TOKEN`, `_KEY`, `_SECRET` or `_PASSWORD`. Any other name-shaped value, such as a
lower-case name or `MY_ENDPOINT` when nothing defines it, may be the secret itself and
is listed as `<withheld-name:FINGERPRINT>`, a stable 12-hex-digit label that never
contains the value. The same guard applies to `env` keys in the JSON MCP configs. It also
records that a server has an inline `oauth.client_secret` (kind `mcp-server-inline-secret`), an `auth`
mode (`oauth` or `chatgpt`, anything else as `<invalid-mode>`; recorded only when
`auth` is set explicitly, the implicit default `oauth` is not assumed) or an
`http_headers_helper` command, never the secret or the command. Try the synthetic fixture with `agent-key-inventory scan --home examples/codex-home --env-names examples/session.env-names`.
This inventories declarations, including disabled servers. It does not resolve
Codex's configuration layers, inspect OAuth storage, or run header helpers.

Codex grant ids start with `mcp:codex/`, for example `mcp:codex/github` and
`mcp:codex/github/env/GITHUB_TOKEN`; servers from the JSON config files keep
`mcp:server/<name>`. A Codex server and a `.mcp.json` server with the same name
are two grants, so a usage log names the one it used: `{"grant": "mcp:codex/github"}`.

## What it does not do

It does not collect usage: the log comes from whatever runs the agent. It does not revoke anything, and it cannot see authority that lives outside the files it knows, such as a browser session or an OS keychain.

## License

MIT.
