package io.diagrid.university.bindings.engineering;

import java.util.concurrent.CountDownLatch;

import io.dapr.client.DaprClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

// Opens once the startup clear is done. Cron ticks and GET requests wait on it, so a ping
// stored by an early tick is never wiped by the clear.
@Component
public class StartupGate {

    private static final Logger log = LoggerFactory.getLogger(StartupGate.class);

    private final CountDownLatch open = new CountDownLatch(1);
    private final DaprClient daprClient;
    private final ShipDb shipDb;

    StartupGate(DaprClient daprClient, ShipDb shipDb) {
        this.daprClient = daprClient;
        this.shipDb = shipDb;
    }

    public void await() {
        try {
            open.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @EventListener(ApplicationReadyEvent.class)
    void clearOnStartup() {
        try {
            // The sidecar starts alongside the app; binding calls only work once it is up.
            daprClient.waitForSidecar(60000).block();
            // Each run starts with an empty table, so pings from an earlier run (or another
            // language) never show up. The app does this itself because Postgres outlives it.
            shipDb.exec(ShipDb.CLEAR_COMMS).block();
            log.info("engineering cleared comms_log for a fresh run");
        } catch (Exception e) {
            log.warn("engineering could not clear comms_log: {}", e.getMessage());
        } finally {
            // Open the gate even when the clear failed: the app keeps running.
            open.countDown();
        }
    }
}
