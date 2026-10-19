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

The example home and project hold six planted values; the separate Codex fixture adds two. All are `PLANTED-SECRET-VALUE-NN`. The test suite runs output modes and fails if any of them appears.

### Codex MCP configuration

Home and explicitly supplied project `.codex/config.toml` files are also inventoried.
The scan includes inline and forwarded environment variable names, bearer-token
variable names, and static HTTP header names. Header values stay private. Try the
synthetic fixture with `agent-key-inventory scan --home examples/codex-home --env-names examples/session.env-names`.
This inventories declarations, including disabled servers. It does not resolve
Codex's configuration layers, inspect OAuth storage, or run header helpers.

Without `--home` and `--env-file` it scans your own home directory and this process's environment. Output stays names and locations, but it is still a map of what your machine can reach, so treat it accordingly.

## What it does not do

It does not collect usage: the log comes from whatever runs the agent. It does not revoke anything, and it cannot see authority that lives outside the files it knows, such as a browser session or an OS keychain.

## License

MIT.
