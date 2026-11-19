package io.diagrid.university.bindings.engineering;

import java.util.List;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// Failed Dapr calls and a malformed minTemp throw; ApiErrors turns them into error responses.
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
    // path is the component name (warp-core-scan). No annotation needed. Returning normally
    // answers 200, and any 2xx tells Dapr the tick was handled.
    @PostMapping("/warp-core-scan")
    public void warpCoreScan() {
        gate.await();
        WarpCoreReading reading = readings.createReading();
        log.info("{}", reading.toLogLine());
        // Output binding: call the component named ship-db with the "exec" operation. The SQL
        // goes in metadata.sql, its values in metadata.params as a JSON array for $1..$4.
        shipDb.exec(ShipDb.INSERT_READING,
                reading.readingId(), reading.stardate(), reading.coreTempK(), reading.plasmaFlow()).block();
        log.info("engineering stored reading {} in warp_core_readings", reading.readingId());
    }

    // A second cron binding drives the clean-up. It is an "exec" again: the delete changes data
    // and returns no rows.
    @PostMapping("/purge-old-readings")
    public void purgeOldReadings() {
        gate.await();
        shipDb.exec(ShipDb.PURGE_READINGS).block();
        log.info("engineering purged old readings");
    }

    @GetMapping("/readings")
    public List<ReadingRow> getReadings(@RequestParam(name = "minTemp", required = false) String minTemp) {
        // Missing minTemp means 0. A present but malformed one (empty, 9.5, abc, too long) is a 400.
        if (minTemp != null && !MIN_TEMP.matcher(minTemp).matches()) {
            throw new ApiErrors.InvalidMinTempException();
        }
        int minTempValue = minTemp == null ? 0 : Integer.parseInt(minTemp);

        gate.await();
        // Output binding again, with the "query" operation: it returns rows. Each row is a
        // list whose values follow the SELECT list, so we map them by position.
        return shipDb.query(ShipDb.SELECT_READINGS, minTempValue).stream()
                .map(row -> new ReadingRow(
                        (String) row.get(0),
                        ((Number) row.get(1)).doubleValue(),
                        ((Number) row.get(2)).intValue(),
                        ((Number) row.get(3)).doubleValue(),
                        (String) row.get(4)))
                .toList();
    }
}
