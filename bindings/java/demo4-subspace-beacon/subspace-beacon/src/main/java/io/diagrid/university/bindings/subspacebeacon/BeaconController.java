package io.diagrid.university.bindings.subspacebeacon;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

// The beacon is a plain HTTP app: no Dapr SDK, no Dapr code. Engineering calls it through
// service invocation, and the Dapr sidecar next to this app delivers the request here.
@RestController
public class BeaconController {

    private static final Logger log = LoggerFactory.getLogger(BeaconController.class);

    // Signal strength walks through a fixed sequence, then stays at the last value. The counter
    // is per process, so restarting the beacon restarts the sequence.
    private static final int[] SEQUENCE = {12, 27, 45, 63, 81, 94};

    private final AtomicInteger calls = new AtomicInteger();

    // Response body. Record components are serialized in declaration order, so the JSON keys
    // come out in the contract's order.
    record Ping(String beaconId, int signalStrength, String message, double stardate) {
    }

    @GetMapping("/ping")
    public Ping ping() {
        int signalStrength = SEQUENCE[Math.min(calls.getAndIncrement(), SEQUENCE.length - 1)];
        String message = signalStrength < 40 ? "static" : signalStrength < 80 ? "signal acquired" : "channel open";
        // Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
        double stardate = Math.round((78000.0 + (Instant.now().getEpochSecond() - 1767225600L) / 3600.0) * 10.0) / 10.0;
        log.info("subspace-beacon answered ping signalStrength={}", signalStrength);
        return new Ping("relay-theta-9", signalStrength, message, stardate);
    }
}
