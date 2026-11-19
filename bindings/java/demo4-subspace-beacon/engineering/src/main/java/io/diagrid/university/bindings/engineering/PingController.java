package io.diagrid.university.bindings.engineering;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.json.JsonMapper;

@RestController
public class PingController {

    private static final Logger log = LoggerFactory.getLogger(PingController.class);

    // What the beacon answers.
    record Ping(String beaconId, int signalStrength, String message, double stardate) {
    }

    // Response body. Record components are serialized in declaration order, so the JSON keys
    // come out in the contract's order. A null lastSignalStrength is written as JSON null.
    record CommsStatus(String status, Integer lastSignalStrength) {
    }

    // One HTTP client for all ticks. It talks to the Dapr sidecar, never to the beacon directly.
    private static final HttpClient httpClient = HttpClient.newHttpClient();
    private static final String DAPR_HTTP_PORT = System.getenv().getOrDefault("DAPR_HTTP_PORT", "3520");

    private final ShipDb shipDb;
    private final StartupGate gate;
    private final JsonMapper mapper;

    PingController(ShipDb shipDb, StartupGate gate, JsonMapper mapper) {
        this.shipDb = shipDb;
        this.gate = gate;
        this.mapper = mapper;
    }

    // Input binding: the beacon-ping cron component makes the sidecar call this plain HTTP
    // endpoint every 5 seconds. The path is the component name. No annotation needed.
    @PostMapping("/beacon-ping")
    public ResponseEntity<?> beaconPing() {
        gate.await();

        Ping ping;
        try {
            // Service invocation: the request goes to our own sidecar. The sidecar resolves the
            // target app from the dapr-app-id header, so there is no host or port of the beacon
            // in this code. The URL path is just the method name "ping".
            HttpRequest request = HttpRequest.newBuilder()
                    .GET()
                    .uri(URI.create("http://localhost:" + DAPR_HTTP_PORT + "/ping"))
                    .header("dapr-app-id", "subspace-beacon")
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException("subspace-beacon answered " + response.statusCode());
            }
            ping = mapper.readValue(response.body(), Ping.class);
        } catch (Exception e) {
            // The beacon may still be starting, so an unreachable beacon is expected: we log it and move on.
            // Answering 200 is deliberate: a 500 would change nothing, because cron ticks are never retried;
            // the next tick simply tries again.
            log.warn("engineering beacon unreachable");
            return ResponseEntity.ok().build();
        }

        try {
            // Output binding: call the component named ship-db with the "exec" operation. The SQL
            // goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
            shipDb.exec(ShipDb.INSERT_PING,
                    ping.beaconId(), ping.signalStrength(), ping.message(), ping.stardate()).block();
            log.info("engineering pinged {} signalStrength={} message=\"{}\"",
                    ping.beaconId(), ping.signalStrength(), ping.message());
        } catch (Exception e) {
            log.warn("engineering binding call failed: {}", e.getMessage());
        }
        return ResponseEntity.ok().build();
    }

    @GetMapping("/comms/status")
    public ResponseEntity<?> commsStatus() {
        gate.await();
        try {
            // Output binding with the "query" operation. Each row is a list whose values follow
            // the SELECT list, so we read the signal by position.
            List<List<Object>> rows = shipDb.query(ShipDb.LAST_PINGS);
            List<Integer> signals = rows.stream().map(row -> ((Number) row.get(0)).intValue()).toList();
            boolean established = signals.size() == 3 && signals.stream().allMatch(signal -> signal >= 40);
            // The newest row is first (ORDER BY id DESC). No rows means null.
            Integer last = signals.isEmpty() ? null : signals.get(0);
            return ResponseEntity.ok(new CommsStatus(established ? "ESTABLISHED" : "SEARCHING", last));
        } catch (Exception e) {
            log.warn("engineering binding call failed: {}", e.getMessage());
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("error", "BINDING_FAILED"));
        }
    }
}
