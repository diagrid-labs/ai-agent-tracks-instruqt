# Bindings demos: risk outcomes

Outcomes of the risks in spec section 7. Each one is filled in when the demo that depends on it is built.

Risks 1, 2, 4 and 5 were probed in Task 2 against a bare sidecar (Dapr runtime 1.19.1, `dapr run --app-id probe --dapr-http-port 3599 --resources-path bindings/python/resources`, `curl` to `POST /v1.0/bindings/ship-db`) and the 1.19 SDK sources. Probe rows and the scratch `state` and `dapr_metadata` tables were removed afterwards.

## 1. `query` result shape

**Verified: an array of arrays (positional), not objects.** Map rows by column position.

`INSERT_READING` with `["wc-9999", 78000.5, 901, 0.88]`, then `SELECT_READINGS` with `[900]`:

```
HTTP/1.1 200 OK
Content-Type: application/json
Metadata.operation: query
Metadata.duration: 9.099ms
...
[["wc-9999",78000.5,901,0.88,"2026-11-19T07:44:40Z"]]
```

Because the SQL casts `stardate::float8`, `plasma_flow::float8` and formats `recorded_at` with `to_char`, every value is a plain JSON string or number: `[readingId:str, stardate:number, coreTempK:int, plasmaFlow:number, recordedAt:str]`. An uncast query (`SELECT reading_id, stardate, plasma_flow, recorded_at ...`) returned `[["wc-9999",78000.5,0.88,"2026-11-19T08:44:40.274299+01:00"]]`, so NUMERIC also came back as a JSON number here and TIMESTAMPTZ as an RFC 3339 string in the server's local zone. The casts remain the safer contract.

## 2. Rows-affected for `exec`

**Verified for the sidecar. The key is `rows-affected` (a string, e.g. `"1"`), in the response metadata of `exec`** (source: components-contrib `bindings/postgres/postgres.go:184`, `resp.Metadata["rows-affected"]`). It is `0` when nothing matched. `query` responses carry no such key.

Raw HTTP response of `exec` (the HTTP API returns response metadata as `Metadata.<key>` headers, with Go header canonicalization, so `rows-affected` appears as `Metadata.rows-Affected`; the body is empty):

```
HTTP/1.1 200 OK
Metadata.duration: 1.794ms
Metadata.end-Time: 2026-11-19T07:44:40.32733Z
Metadata.operation: exec
Metadata.rows-Affected: 1
Metadata.sql: DELETE FROM warp_core_readings
Metadata.start-Time: 2026-11-19T07:44:40.325536Z
Content-Length: 0
```

A second `DELETE FROM warp_core_readings` on the empty table returned `Metadata.rows-Affected: 0`. Over gRPC (what the SDKs use) the key is the original `rows-affected`.

**Per-SDK exposure of response metadata (SDKs read at v1.19.1 .NET, v1.19.0 Python and Java):**

| SDK | Exposes `rows-affected`? | Evidence |
|---|---|---|
| .NET `Dapr.Client` | **Yes.** `InvokeBindingAsync(BindingRequest)` returns `BindingResponse` with `IReadOnlyDictionary<string,string> Metadata`; read `response.Metadata["rows-affected"]`. | `src/Dapr.Client/DaprClientGrpc.cs:320-326` builds `new BindingResponse(request, response.Data.Memory, response.Metadata)`; `src/Dapr.Client/BindingResponse.cs:26,41` declares the `Metadata` property. The overloads at `DaprClient.cs:303` and `:321` (generic) return nothing or only the deserialized data. |
| Python `DaprClient.invoke_binding` | **Yes.** Returns `BindingResponse`; read `resp.binding_metadata['rows-affected']`. | `dapr/clients/grpc/client.py:419` (`return BindingResponse(response.data, dict(response.metadata), call.initial_metadata())`); `dapr/clients/grpc/_response.py:312` (`binding_metadata` property). |
| Java `io.dapr:dapr-sdk` 1.19.0 | **No.** No overload returns the response metadata. | Every `DaprClient.invokeBinding` overload (`DaprClient.java:396, 407, 419, 431, 444, 458, 467, 477`) returns `Mono<Void>`, `Mono<byte[]>` or `Mono<T>` (the deserialized data only). The implementation, `DaprClientImpl.java:763-815`, reads `it.getMetadataMap()` only to look up `statusCode` for HTTP-binding errors (line 797-798) and returns `it.getData()` deserialized (line 807). `InvokeBindingRequest` has request metadata only (`getMetadata`/`setMetadata`, `InvokeBindingRequest.java:60,64`). `DaprPreviewClient` has no `invokeBinding` at all. The `responseMetadata` at line 786 is gRPC trailer/header metadata, not the binding's response map. |

**Consequence: Java cannot read the rows-affected count through the SDK, so spec §7 risk 2 applies to Java.** Decision (user, 2026-11-19): **no count. The purge stays an `exec` and every language logs `engineering purged old readings`.**

## 3. Cron behaviour on failure

**Verified (Task 3, .NET, Dapr 1.19.1): a `500` from the handler is not retried and does not move the schedule.** The handler was temporarily changed to log the reading and return `500`; the demo ran 38 s with `@every 10s`. The app saw exactly three `POST /warp-core-scan` requests (all answered `500`), one per tick, and no extra request between ticks. daprd logged nothing about the failures at its default level (no warning, no error line), so a failing handler is invisible in the sidecar log. Only the app log shows the `500`. The handler was reverted afterwards.

## 4. `params` metadata

**Verified (raw sidecar API): `metadata.params` is a JSON array encoded as a string.** String and number elements both work, with `$1`-style placeholders:

- `exec`, `"params":"[\"wc-9999\", 78000.5, 901, 0.88]"` inserted one row (`rows-affected: 1`).
- `query`, `"params":"[900]"` (number) and `"params":"[\"900\"]"` (string) both matched the row; Postgres casts the parameter to the column type.
- No `params` key works for statements without placeholders (`CLEAR_READINGS`).

The SDK side is a plain `Map<String,String>` of request metadata in all three SDKs (.NET `BindingRequest.Metadata`, Python `binding_metadata`, Java `InvokeBindingRequest.setMetadata`), so the same string passes through unchanged. Whether each SDK's serialization of the array string matches is confirmed in Task 3 when the apps exist.

## 5. `state.postgresql` v1 vs v2

**Verified: v1 is loadable in 1.19.1** with a component of `type: state.postgresql`, `version: v1`, only `connectionString` set. The sidecar log shows `Component loaded: statestore (state.postgresql/v1)` and creates the `dapr_metadata` and `state` tables. `value` is JSONB, readable in `psql`.

`POST /v1.0/state/statestore` with `[{"key":"reading-wc-0001","value":{"readingId":"wc-0001","coreTempK":900}}]` returned `204`, and `GET /v1.0/state/statestore/reading-wc-0001` returned `{"coreTempK": 900, "readingId": "wc-0001"}`.

`\d state`:

```
   Column   |           Type           | Nullable |             Default
------------+--------------------------+----------+----------------------------------
 key        | text                     | not null |
 value      | jsonb                    | not null |
 isbinary   | boolean                  | not null |
 insertdate | timestamp with time zone | not null | now()
 updatedate | timestamp with time zone |          |
 expiredate | timestamp with time zone |          |
 row_id     | bigint                   | not null | generated by default as identity
Indexes: "state_pkey" PRIMARY KEY (key), "state_row_id_uidx" UNIQUE (row_id)
```

`SELECT key, value FROM state`:

```
          key           |                   value
------------------------+--------------------------------------------
 probe||reading-wc-0001 | {"coreTempK": 900, "readingId": "wc-0001"}
```

**State key format: `<app-id>||<key>`.** For the Demo 3 assertion the app-id is `engineering`, so the row key is `engineering||reading-wc-0001`. Note: the JSONB column normalises key order (`coreTempK` before `readingId`), so assert on values, not on text.

Task 3 must remember: the `state` and `dapr_metadata` tables are created by the sidecar on first use and were dropped after the probe, so the smoke tests must not assume they exist before the demo runs.

## 6. Input-binding route probing

**Verified (Task 3, all three languages): no `OPTIONS` probe is sent, and the cron binding needs no route registration.** At startup daprd only requested `GET /dapr/config` (answered `404` by the .NET app, which is fine) and logged `successful init for input binding (warp-core-scan (bindings.cron/v1))`. The first `POST /warp-core-scan` arrived one full interval (10 s) after startup, with no `OPTIONS /warp-core-scan` in the app log. The route is simply `POST /<component name>`; a plain minimal-API / FastAPI / Spring `@PostMapping` endpoint works with no Dapr attribute, decorator or SDK in any of the three languages. The cron binding sends `Content-Type: application/json` with an empty body.
