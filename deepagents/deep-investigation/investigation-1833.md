# Investigation of Issue #1833 - Data Corruption in Actor/Service Invocation Under High RPS

## Summary
Issue #1833 was reported regarding unexpected data corruption during actor service invocations, primarily under high request per second (RPS) conditions (estimated >1000 RPS). The report highlighted incorrect serialization leading to malformed JSON responses. This behavior was witnessed in the context of using the Dapr Python SDK.

**Reported Occurrences:**
1. Duplicate brackets in the received JSON response.
2. JSONDecodeError due to additional data after the expected structure.

Main author of the issue: [XavierGeerinck](https://github.com/XavierGeerinck)

## Probable Root Cause
The root cause appears to stem from overlapping responses during concurrent invocations, specifically related to the asynchronous handling of requests using the aiohttp library. Multiple invocation requests arriving back-to-back can lead to responses overlapping in memory, resulting in corrupted data being delivered to the client.

The investigation identified:
- **Session Mismanagement**: Improper handling of asynchronous calls against a single event loop may lead to futures being attached to different loops, causing runtime exceptions.
- **Response Overlap**: The Dapr sidecar service seems to return the wrong response body when requests are processed in rapid succession, indicating that the handling of asynchronous responses requires further refinement when under load.

## Related Work
- **Linked PRs**:
  - [#1839](https://github.com/dapr/dapr/pull/1839): Clone appchannel response body to prevent GC. This PR aims to mitigate overlapping responses during actor invocations, though it has been noted that the underlying issue may relate to broader http server implementation challenges.

## Suggested Next Steps
1. **Testing Under Load**: Conduct further tests simulating high RPS to validate the behavior with various concurrency models.
2. **Asynchronous Call Improvements**: Explore other asynchronous patterns or libraries to better manage the event loop and thread safety issues.
3. **Review HTTP Server Implementation**: Evaluate if changes to the HTTP server could resolve lingering inconsistencies. Further investigation into the aiohttp library may be necessary, possibly lifting some code for better handling in Dapr's architecture.
4. **User Communication**: Notify users of the temporary workaround implemented in PR #1839 and inform them of ongoing investigations to improve stability in high-throughput scenarios.

---
Generated on: [Date of report generation]