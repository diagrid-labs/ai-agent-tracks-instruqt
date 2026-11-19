package io.diagrid.university.bindings.engineering;

import java.util.List;

import io.dapr.exceptions.DaprException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

// A failed Dapr call in GET /comms/status throws; ApiErrors turns it into an error response.
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

    private final RestClient beacon;
    private final ShipDb shipDb;
    private final StartupGate gate;

    PingController(RestClient beaconClient, ShipDb shipDb, StartupGate gate) {
        this.beacon = beaconClient;
        this.shipDb = shipDb;
        this.gate = gate;
    }

    // Input binding: the beacon-ping cron component makes the sidecar call this plain HTTP
    // endpoint every 5 seconds. The path is the component name. No annotation needed.
    // This method always answers 200: a 500 would change nothing, because cron ticks are never
    // retried; the next tick simply tries again.
    @PostMapping("/beacon-ping")
    public void beaconPing() {
        gate.await();

        Ping ping;
        try {
            // Service invocation: the request goes to our own sidecar, which forwards it to the
            // app with ID subspace-beacon (see beaconClient). The path is just the method name.
            ping = beacon.get().uri("/ping").retrieve().body(Ping.class);
        } catch (RestClientException e) {
            // The beacon may still be starting, so an unreachable beacon is expected: we log it and move on.
            log.warn("engineering beacon unreachable");
            return;
        }

        try {
            // Output binding: call the component named ship-db with the "exec" operation. The SQL
            // goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
            shipDb.exec(ShipDb.INSERT_PING,
                    ping.beaconId(), ping.signalStrength(), ping.message(), ping.stardate()).block();
            log.info("engineering pinged {} signalStrength={} message=\"{}\"",
                    ping.beaconId(), ping.signalStrength(), ping.message());
        } catch (DaprException e) {
            log.warn("engineering binding call failed: {}", e.getMessage());
        }
    }

    @GetMapping("/comms/status")
    public CommsStatus commsStatus() {
        gate.await();
        // Output binding with the "query" operation. Each row is a list whose values follow
        // the SELECT list, so we read the signal by position.
        List<Integer> signals = shipDb.query(ShipDb.LAST_PINGS).stream()
                .map(row -> ((Number) row.get(0)).intValue())
                .toList();
        boolean established = signals.size() == 3 && signals.stream().allMatch(signal -> signal >= 40);
        // The newest row is first (ORDER BY id DESC). No rows means null.
        Integer last = signals.isEmpty() ? null : signals.get(0);
        return new CommsStatus(established ? "ESTABLISHED" : "SEARCHING", last);
    }
}
