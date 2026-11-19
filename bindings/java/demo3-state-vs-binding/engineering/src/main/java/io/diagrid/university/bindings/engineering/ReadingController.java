package io.diagrid.university.bindings.engineering;

import java.util.List;
import java.util.regex.Pattern;

import io.dapr.client.DaprClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// Failed Dapr calls, a malformed minTemp and an unknown reading throw; ApiErrors turns them
// into error responses.
@RestController
public class ReadingController {

    private static final Logger log = LoggerFactory.getLogger(ReadingController.class);
    private static final Pattern MIN_TEMP = Pattern.compile("-?[0-9]{1,6}");

    // Response body. Record components are serialized in declaration order, so the JSON keys
    // come out in the contract's order.
    record ReadingRow(String readingId, double stardate, int coreTempK, double plasmaFlow, String recordedAt) {
    }

    // The state store component name, from resources/statestore.yaml.
    private static final String STATE_STORE = "statestore";

    private static String stateKey(String readingId) {
        return "reading-" + readingId;
    }

    private final ReadingFactory readings;
    private final DaprClient daprClient;
    private final ShipDb shipDb;
    private final StartupGate gate;

    ReadingController(ReadingFactory readings, DaprClient daprClient, ShipDb shipDb, StartupGate gate) {
        this.readings = readings;
        this.daprClient = daprClient;
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

        // The same reading is written twice, through two different Dapr APIs.
        //
        // 1. State API: Dapr owns the table. We hand over a key and a value, Dapr decides how
        //    to store it (a `state` table with key, JSON value and timestamps; the ETag is Postgres's
        //    hidden xmin column, so \d state doesn't list it). There
        //    is no schema and no SQL in our code, and the call is portable: swap the
        //    statestore component for Redis or Cosmos DB and this line stays the same. The
        //    API also gives us ETags, TTL and transactions for free.
        String key = stateKey(reading.readingId());
        // The Java SDK sets contentType: application/json itself, so there is no metadata to pass.
        daprClient.saveState(STATE_STORE, key, reading).block();
        log.info("engineering saved reading {} to statestore (key={})", reading.readingId(), key);

        // 2. Output binding: we own the table. We wrote the schema and we write the SQL, so we
        //    can filter, sort and delete in bulk (see GET /readings). The price is that this
        //    code is tied to Postgres: swapping the ship-db component for another store breaks it.
        shipDb.exec(ShipDb.INSERT_READING,
                reading.readingId(), reading.stardate(), reading.coreTempK(), reading.plasmaFlow()).block();
        log.info("engineering stored reading {} in warp_core_readings", reading.readingId());
    }

    // State API read: one reading by key. The State API reads by key (one or in bulk). Filtering on
    // values needs the alpha State Query API, which this track doesn't use; with the binding it's a
    // one-line WHERE (see GET /readings).
    @GetMapping("/state/{readingId}")
    public WarpCoreReading getState(@PathVariable("readingId") String readingId) {
        gate.await();
        WarpCoreReading reading = daprClient
                .getState(STATE_STORE, stateKey(readingId), WarpCoreReading.class)
                .block()
                .getValue();
        // A key that was never saved comes back with a null value, not as an error.
        if (reading == null) {
            throw new ApiErrors.ReadingNotFoundException();
        }
        return reading;
    }

    // Binding read, with SQL: the filter and the ordering are ours, so "all readings above 900 K"
    // is a one-line WHERE. The State API would need the alpha State Query API for that.
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
