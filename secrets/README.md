# Dapr Secrets demos

Demo apps for the Dapr University `dapr-secrets` track, in .NET, Python and Java. They show how the Dapr Secrets API reads a secret, how scoping refuses an app, and how the secret provider can change without touching application code.

In Instruqt the sandbox setup script prepares everything below for you. Use this guide to run the demos on your own machine.

## Prerequisites

- [Dapr CLI](https://docs.dapr.io/getting-started/install-dapr-cli/) 1.18 and a completed `dapr init` (Docker required)
- Docker, for the HashiCorp Vault container used in challenge 4
- The runtime for the language you want to run: .NET SDK 10, Python 3.12 with [uv](https://docs.astral.sh/uv/), or Java 17 with Maven

The shell commands below assume a POSIX shell (Git Bash, WSL, macOS or Linux) with `python3` available. The track itself runs on a Linux sandbox.

## Create `secrets.json`

The local file secret store reads `secrets/secrets.json`, which is not committed. Copy the template, which already holds the fake demo values (the sandbox setup script does the same):

```bash
cp secrets/secrets.example.json secrets/secrets.json
```

## Start Vault (challenge 4 only)

```bash
# Dev-mode Vault keeps nothing across restarts, so removing any existing
# container first makes this block safe to run again.
docker rm -f vault >/dev/null 2>&1 || true
docker run -d --name vault -p 8200:8200 --cap-add=IPC_LOCK \
  -e VAULT_DEV_ROOT_TOKEN_ID=root -e VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
  hashicorp/vault:1.20
# Wait up to 30 seconds for Vault to answer, then seed it
vault_ready=false
for _ in $(seq 1 30); do
  if docker exec -e VAULT_ADDR=http://127.0.0.1:8200 vault vault status >/dev/null 2>&1; then
    vault_ready=true
    break
  fi
  sleep 1
done
if [ "$vault_ready" != "true" ]; then
  echo "ERROR: Vault did not become ready within 30 seconds. Check 'docker logs vault'." >&2
else
  # Seed Vault with the same secrets as secrets/secrets.json
  python3 -c 'import json; [print(k, v) for k, v in json.load(open("secrets/secrets.json")).items()]' | \
    tr -d '\r' | while read -r name value; do
      docker exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=root vault \
        vault kv put "secret/dapr/$name" "$name=$value" </dev/null
    done
fi
```

The secret names and values come from `secrets.example.json`, which is the single source for both stores.

## Demos

| Folder | Used in | What it shows |
|---|---|---|
| `Demo1-ReadSecret` | Challenges 1 and 2 | One app reads a secret from the `secretstore` component |
| `Demo2-Scoping` | Challenge 3 | Two apps, one allowed to read a secret and one refused |
| `Demo3-SwapProvider` | Challenge 4 | The unchanged `Demo1-ReadSecret` app, run with a `secretstore` component that points at HashiCorp Vault instead of a file |

Each language has its own folder (`dotnet/`, `python/`, `java/`) containing all three demos and a `resources/` folder with the component YAML.

`Demo3-SwapProvider` has no application code. Its `dapr.yaml` starts `../Demo1-ReadSecret` with its own `resources` folder, where `secretstore-vault.yaml` is the `secretstore` component. It is not in the shared `resources` folder because a sidecar does not start when two components there have the same name.

## Run a demo

Run the demos from inside the demo folder. The apps are added to this repo as the track is built, so a folder may not exist yet.

```bash
# .NET
cd secrets/dotnet/Demo1-ReadSecret && dapr run -f .

# Python
cd secrets/python/Demo1-ReadSecret && dapr run -f .

# Java
cd secrets/java/Demo1-ReadSecret && dapr run -f .
```

Replace `Demo1-ReadSecret` with `Demo2-Scoping` for the scoping demo, or with `Demo3-SwapProvider` for the Vault demo (start Vault first, see above).
