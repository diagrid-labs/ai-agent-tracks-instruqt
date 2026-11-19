package io.diagrid.university.bindings.engineering;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReadingController {

    private static final Logger log = LoggerFactory.getLogger(ReadingController.class);
    private static final Pattern MIN_TEMP = Pattern.compile("-?[0-9]{1,6}");

    // Response body. Record components are serialized in declaration order, so the JSON keys
    // come out in the contract's order.
    record ReadingRow(String readingId, double stardate, int coreTempK, double plasmaFlow, String recordedAt) {
    }

    private final ReadingFactory readings;
    private final ShipDb shipDb;
    private final StartupGate gate;

    ReadingController(ReadingFactory readings, ShipDb shipDb, StartupGate gate) {
        this.readings = readings;
        this.shipDb = shipDb;
        this.gate = gate;
    }

    // An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
    // path is the component name (warp-core-scan). No annotation needed.
    @PostMapping("/warp-core-scan")
    public ResponseEntity<?> warpCoreScan() {
        gate.await();
        WarpCoreReading reading = readings.createReading();
        log.info("{}", reading.toLogLine());
        try {
            // Output binding: call the component named ship-db with the "exec" operation. The SQL
            // goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
            shipDb.exec(ShipDb.INSERT_READING,
                    reading.readingId(), reading.stardate(), reading.coreTempK(), reading.plasmaFlow()).block();
        } catch (Exception e) {
            return bindingFailed(e);
        }
        log.info("engineering stored reading {} in warp_core_readings", reading.readingId());
        // Any 2xx tells Dapr the tick was handled.
        return ResponseEntity.ok().build();
    }

    // A second cron binding drives the clean-up. It is an "exec" again: the delete changes data
    // and returns no rows.
    @PostMapping("/purge-old-readings")
    public ResponseEntity<?> purgeOldReadings() {
        gate.await();
        try {
            shipDb.exec(ShipDb.PURGE_READINGS).block();
        } catch (Exception e) {
            return bindingFailed(e);
        }
        log.info("engineering purged old readings");
        return ResponseEntity.ok().build();
    }

    @GetMapping("/readings")
    public ResponseEntity<?> getReadings(@RequestParam(name = "minTemp", required = false) String minTemp) {
        // Missing minTemp means 0. A present but malformed one (empty, 9.5, abc, too long) is a 400.
        int minTempValue = 0;
        if (minTemp != null) {
            if (!MIN_TEMP.matcher(minTemp).matches()) {
                return ResponseEntity.badRequest().body(Map.of("error", "INVALID_MIN_TEMP"));
            }
            minTempValue = Integer.parseInt(minTemp);
        }

        gate.await();
        try {
            // Output binding again, with the "query" operation: it returns rows. Each row is a
            // list whose values follow the SELECT list, so we map them by position.
            List<List<Object>> rows = shipDb.query(ShipDb.SELECT_READINGS, minTempValue);
            List<ReadingRow> body = rows.stream()
                    .map(row -> new ReadingRow(
                            (String) row.get(0),
                            ((Number) row.get(1)).doubleValue(),
                            ((Number) row.get(2)).intValue(),
                            ((Number) row.get(3)).doubleValue(),
                            (String) row.get(4)))
                    .toList();
            return ResponseEntity.ok(body);
        } catch (Exception e) {
            return bindingFailed(e);
        }
    }

    private ResponseEntity<?> bindingFailed(Exception e) {
        log.warn("engineering binding call failed: {}", e.getMessage());
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("error", "BINDING_FAILED"));
    }
}
