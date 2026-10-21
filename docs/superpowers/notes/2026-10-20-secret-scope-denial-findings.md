# Secret scope denial: findings

Spike for the Dapr Secrets track (spec 3.1 and 7.3). Question: what does an app receive when secret scoping denies it a secret, and can it be told apart from a secret that does not exist?

## Verdict

**A denied secret is visibly distinct from a genuinely missing secret.** The track's core premise holds, with one caveat that challenge 3 must respect (see "Caveat").

| Situation | HTTP | `errorCode` | gRPC status |
|---|---|---|---|
| Allowed and exists | 200 | n/a | OK |
| **Denied by scope** | **403 Forbidden** | **`ERR_PERMISSION_DENIED`** | **`PERMISSION_DENIED`** |
| Permitted by scope but not in the store | 500 Internal Server Error | `ERR_SECRET_GET` | `INTERNAL` |

### Caveat: deny-by-default hides missing secrets

The scope check runs before the store lookup. With `defaultAccess: deny`, any name not in `allowedSecrets` gets 403 `ERR_PERMISSION_DENIED`, **whether or not the secret exists in the store**. So `app-b` asking for a name that exists nowhere (`does-not-exist`) is also refused with 403. "Not found" is only visible for a name the scope permits. Challenge 3 should use a real secret (`orderdb-password`) for the denial demo and must not suggest that 403 proves the secret exists.

## Environment

- Host: WSL2 Ubuntu (kernel 6.18.54.1-microsoft-standard-WSL2), x86_64
- Dapr CLI 1.18.3, runtime (`daprd --version`) **1.18.7**, installed with `dapr init --slim --runtime-version 1.18.7` into an isolated runtime path. `daprd` was started directly. No Docker containers were used (the local file secret store needs none).
- .NET SDK 10.0.107, `Dapr.Client` **1.18.10**
- Python 3.10.6, `dapr` **1.18.3** (grpcio 1.84.0)
- Java OpenJDK 25.0.2 (compiled for release 17), Maven 3.6.3, `io.dapr:dapr-sdk` **1.18.1**
- All three SDKs used their default gRPC transport against the sidecar's gRPC port.

## Setup

`secrets.json` (fake demo values):

```json
{
  "orderdb-password": "orderdb-s3cret-demo",
  "payments-api-key": "pk_demo_0123456789"
}
```

`components/secretstore.yaml`:

```yaml
apiVersion: dapr.io/v1alpha1
kind: Component
metadata:
  name: secretstore
spec:
  type: secretstores.local.file
  version: v1
  metadata:
  - name: secretsFile
    value: <absolute path to secrets.json>
  - name: nestedSeparator
    value: ":"
```

`config-b.yaml` (the configuration for `app-b`):

```yaml
apiVersion: dapr.io/v1alpha1
kind: Configuration
metadata:
  name: app-b-config
spec:
  secrets:
    scopes:
    - storeName: secretstore
      defaultAccess: deny
      allowedSecrets: ["payments-api-key"]
```

Sidecar: `daprd --app-id app-b --dapr-http-port 3500 --dapr-grpc-port 50001 --resources-path ./components --config ./config-b.yaml`

Three extra sidecars were run for comparison (same component, different configuration):

- `app-a`: empty `spec: {}` configuration (no scoping), HTTP 3510.
- `app-c`: `defaultAccess: allow`, `deniedSecrets: ["orderdb-password"]`, HTTP 3520.
- `app-ghost`: `defaultAccess: deny`, `allowedSecrets: ["payments-api-key", "ghost-secret"]` where `ghost-secret` is not in `secrets.json`, HTTP 3530, gRPC 50013.

## Raw HTTP (step 3), as `app-b`

Allowed secret, for contrast:

```
$ curl -i http://localhost:3500/v1.0/secrets/secretstore/payments-api-key
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 42

{"payments-api-key":"pk_demo_0123456789"}
```

**Denied secret** (exists in the store, not in `allowedSecrets`):

```
$ curl -i http://localhost:3500/v1.0/secrets/secretstore/orderdb-password
HTTP/1.1 403 Forbidden
Content-Type: application/json
Content-Length: 122

{"errorCode":"ERR_PERMISSION_DENIED","message":"access denied by policy to get \"orderdb-password\" from \"secretstore\""}
```

The body is the literal JSON above (the backslashes are real JSON escapes). The `Traceparent` and `Date` headers are omitted here; they vary.

Bulk get as `app-b` returns only the permitted secret, with no error and no mention of the filtered one:

```
$ curl -i http://localhost:3500/v1.0/secrets/secretstore/bulk
HTTP/1.1 200 OK

{"payments-api-key":{"payments-api-key":"pk_demo_0123456789"}}
```

## Denied vs missing (step 5)

Missing name asked of `app-b` (not in `secrets.json`, not in `allowedSecrets`):

```
$ curl -i http://localhost:3500/v1.0/secrets/secretstore/does-not-exist
HTTP/1.1 403 Forbidden
Content-Type: application/json
Content-Length: 120

{"errorCode":"ERR_PERMISSION_DENIED","message":"access denied by policy to get \"does-not-exist\" from \"secretstore\""}
```

This is identical to the denied response except for the secret name. Deny-by-default cannot tell "forbidden" from "absent".

Genuinely missing secret that the scope permits (`app-ghost`, sidecar on 3530):

```
$ curl -i http://localhost:3530/v1.0/secrets/secretstore/ghost-secret
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Content-Length: 147

{"errorCode":"ERR_SECRET_GET","message":"failed getting secret with key ghost-secret from secret store secretstore: secret ghost-secret not found"}
```

The same not-found response appears with no scoping at all (`app-a`, 3510, name `does-not-exist`) and with a deny-list scope (`app-c`, 3520, name `does-not-exist`):

```
HTTP/1.1 500 Internal Server Error
Content-Length: 151

{"errorCode":"ERR_SECRET_GET","message":"failed getting secret with key does-not-exist from secret store secretstore: secret does-not-exist not found"}
```

Other scope shapes give the same denial as `app-b`. `app-c` (deny-list) asking for `orderdb-password`:

```
HTTP/1.1 403 Forbidden
Content-Length: 122

{"errorCode":"ERR_PERMISSION_DENIED","message":"access denied by policy to get \"orderdb-password\" from \"secretstore\""}
```

`app-a` (unscoped) reading `orderdb-password` gets 200 with `{"orderdb-password":"orderdb-s3cret-demo"}`, which is the "app-a succeeds, app-b is refused" contrast for challenge 3.

Unrelated, for reference: an unknown store name returns 401 with `{"errorCode":"ERR_SECRET_STORE_NOT_FOUND","message":"failed finding secret store with key nostore"}`.

## SDK behaviour (step 4)

Each call: `GetSecret("secretstore", name)` against `app-b`'s gRPC port 50001, except the ghost row (port 50013). Message text below is verbatim.

### .NET (`Dapr.Client` 1.18.10, `DaprClient.GetSecretAsync`)

Denied (`orderdb-password`) raises `Dapr.DaprException`:

- `Message`: `Secret operation failed: the Dapr endpoint indicated a failure. See InnerException for details.`
- `InnerException` type: `Grpc.Core.RpcException`
- `InnerException.Message`: `Status(StatusCode="PermissionDenied", Detail="access denied by policy to get "orderdb-password" from "secretstore"")`
- `RpcException.StatusCode`: `PermissionDenied`; `Status.Detail`: `access denied by policy to get "orderdb-password" from "secretstore"`

Missing but permitted (`ghost-secret`) raises the same `Dapr.DaprException` with the same outer `Message`; the inner `RpcException` has `StatusCode=Internal` and `Detail=failed getting secret with key ghost-secret from secret store secretstore: secret ghost-secret not found`.

Because the outer message is identical in both cases, a .NET test must inspect `InnerException` (the `RpcException` `StatusCode`) to distinguish them. Missing-and-not-allowed (`does-not-exist` as `app-b`) gives `PermissionDenied` with `Detail=access denied by policy to get "does-not-exist" from "secretstore"`.

### Python (`dapr` 1.18.3, `DaprClient.get_secret`)

Denied (`orderdb-password`) raises `grpc._channel._InactiveRpcError` (no Dapr wrapper). `str(e)` is exactly:

```
<_InactiveRpcError of RPC that terminated with:
	status = StatusCode.PERMISSION_DENIED
	details = "access denied by policy to get "orderdb-password" from "secretstore""
	debug_error_string = "PERMISSION_DENIED:access denied by policy to get "orderdb-password" from "secretstore""
>
```

- `e.code()`: `StatusCode.PERMISSION_DENIED`
- `e.details()`: `access denied by policy to get "orderdb-password" from "secretstore"`

Missing but permitted (`ghost-secret`): same exception class, `e.code()` is `StatusCode.INTERNAL`, `e.details()` is `failed getting secret with key ghost-secret from secret store secretstore: secret ghost-secret not found`.

Missing-and-not-allowed (`does-not-exist` as `app-b`): `StatusCode.PERMISSION_DENIED`, details `access denied by policy to get "does-not-exist" from "secretstore"`.

Note `code` and `details` are methods on the gRPC exception, not attributes.

### Java (`io.dapr:dapr-sdk` 1.18.1, `DaprClient.getSecret(...).block()`)

Denied (`orderdb-password`) raises `io.dapr.exceptions.DaprException`:

- `getMessage()`: `PERMISSION_DENIED: access denied by policy to get "orderdb-password" from "secretstore"`
- cause chain: `java.util.concurrent.ExecutionException` (`io.grpc.StatusRuntimeException: PERMISSION_DENIED: access denied by policy to get "orderdb-password" from "secretstore"`), then `io.grpc.StatusRuntimeException` (`PERMISSION_DENIED: access denied by policy to get "orderdb-password" from "secretstore"`)
- a suppressed `java.lang.Exception` with message `#block terminated with an error` (added by Reactor's `block()`)

Missing but permitted (`ghost-secret`): `DaprException`, `getMessage()` is `INTERNAL: failed getting secret with key ghost-secret from secret store secretstore: secret ghost-secret not found`.

Missing-and-not-allowed (`does-not-exist` as `app-b`): `PERMISSION_DENIED: access denied by policy to get "does-not-exist" from "secretstore"`.

Unlike .NET, the Java message itself carries the gRPC code prefix, so a message-contains assertion works.

### Summary table

| SDK | Exception (denied) | What to assert |
|---|---|---|
| .NET | `Dapr.DaprException` wrapping `Grpc.Core.RpcException` | inner `StatusCode == PermissionDenied` |
| Python | `grpc._channel._InactiveRpcError` | `e.code() == grpc.StatusCode.PERMISSION_DENIED` |
| Java | `io.dapr.exceptions.DaprException` | message starts with `PERMISSION_DENIED:` |
| HTTP | 403 | body contains `ERR_PERMISSION_DENIED` |

## Assertion guidance for challenge 3

- The stable marker across HTTP and all SDKs is the string `access denied by policy to get "<name>" from "<store>"` plus the code `ERR_PERMISSION_DENIED` (HTTP) / `PERMISSION_DENIED` (gRPC).
- Match on `PERMISSION_DENIED` rather than the full message if the test must tolerate secret-name changes.
- Use `orderdb-password` for the denial demo, and the secret-store name `secretstore` as in this spike.
- This spike did not test the SDKs over HTTP transport; Python and Java output above came from gRPC.
- The 1.18.7 runtime behaviour was measured once; the message wording is not documented by Dapr, so pin the runtime version in the track.
