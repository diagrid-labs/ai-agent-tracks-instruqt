# Dapr 101 demo apps

Demo apps for the Dapr 101 lab in Dapr University. They are copies of the Dapr quickstarts, from
[`dapr/quickstarts`](https://github.com/dapr/quickstarts) at commit `a7aab42020f3a77e106283292e85f27b6a4444a9` (`master`).

| Folder | Upstream path |
| --- | --- |
| `dotnet/ServiceInvocation` | `service_invocation/csharp/http` |
| `dotnet/PubSub` | `pub_sub/csharp/sdk` |
| `python/service-invocation` | `service_invocation/python/http` |
| `python/pub-sub` | `pub_sub/python/sdk` |
| `java/service-invocation` | `service_invocation/java/http` |
| `java/pub-sub` | `pub_sub/java/sdk` |
| `javascript/service-invocation` | `service_invocation/javascript/http` |
| `javascript/pub-sub` | `pub_sub/javascript/sdk` |

Each folder holds `checkout/`, `order-processor/` and a `dapr.yaml`. Each pub/sub folder also holds
`resources/pubsub.yaml`, copied from `pub_sub/components/pubsub.yaml`. The upstream `makefile` and
`README.md` files are left out.

## Changes from upstream

- The .NET projects target `net10.0` instead of `net8.0`.
- The pub/sub `dapr.yaml` files use `resourcesPaths: ["./resources"]` instead of `resourcesPath: ../../components/`.
- `python/pub-sub` no longer has the `order-processor-fastapi` subscriber, and its uv workspace and `uv.lock` are updated to match.
- The JavaScript `package.json` files no longer have the upstream `start:dapr` script, which `dapr.yaml` does not use (it runs `npm run start`).
