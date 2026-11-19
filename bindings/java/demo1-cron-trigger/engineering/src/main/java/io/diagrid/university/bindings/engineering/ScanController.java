package io.diagrid.university.bindings.engineering;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScanController {

    private static final Logger log = LoggerFactory.getLogger(ScanController.class);

    private final ReadingFactory readings;

    public ScanController(ReadingFactory readings) {
        this.readings = readings;
    }

    // An input binding needs no Dapr code at all: the sidecar calls a plain HTTP endpoint whose
    // path is the component name (warp-core-scan). No annotation, no Dapr SDK.
    @PostMapping("/warp-core-scan")
    public ResponseEntity<Void> warpCoreScan() {
        log.info("{}", readings.createReading().toLogLine());
        // Any 2xx tells Dapr the tick was handled.
        return ResponseEntity.ok().build();
    }
}
