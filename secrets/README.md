# Dapr Secrets demos

Demo apps for the Dapr University `dapr-secrets` track, in .NET, Python and Java. They show how the Dapr Secrets API reads a secret, how scoping refuses an app, and how the secret provider can change without touching application code.

In Instruqt the sandbox setup script prepares everything below for you. Use this guide to run the demos on your own machine.

## Prerequisites

- [Dapr CLI](https://docs.dapr.io/getting-started/install-dapr-cli/) 1.18 and a completed `dapr init` (Docker required)
- Docker, for the HashiCorp Vault container used in challenge 4
- The runtime for the language you want to run: .NET SDK 10, Python 3.12 with [uv](https://docs.astral.sh/uv/), or Java 17 with Maven

## Create `secrets.json`

The local file secret store reads `secrets/secrets.json`, which is not committed. Copy the template and fill in the demo values:

```bash
cp secrets/secrets.example.json secrets/secrets.json
```

```json
{
  "orderdb-password": "s3cr3t-pa55w0rd",
  "payments-api-key": "pk-test-7f3a9"
}
```

## Start Vault (challenge 4 only)

```bash
docker run -d --name vault -p 8200:8200 --cap-add=IPC_LOCK \
  -e VAULT_DEV_ROOT_TOKEN_ID=root -e VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
  hashicorp/vault:1.20
docker exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=root vault \
  vault kv put secret/dapr/orderdb-password orderdb-password=s3cr3t-pa55w0rd
docker exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=root vault \
  vault kv put secret/dapr/payments-api-key payments-api-key=pk-test-7f3a9
```

## Demos

| Folder | Used in | What it shows |
|---|---|---|
| `Demo1-ReadSecret` | Challenges 1, 2 and 4 | One app reads a secret from the `secretstore` component |
| `Demo2-Scoping` | Challenge 3 | Two apps, one allowed to read a secret and one refused |

Each language has its own folder (`dotnet/`, `python/`, `java/`) containing both demos and a `resources/` folder with the component YAML.

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

Replace `Demo1-ReadSecret` with `Demo2-Scoping` for the scoping demo.
