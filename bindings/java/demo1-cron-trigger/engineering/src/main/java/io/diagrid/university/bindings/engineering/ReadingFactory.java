package io.diagrid.university.bindings.engineering;

import java.time.Instant;
import java.util.Locale;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

// Creates readings with a per-process counter, so the first one is wc-0001.
@Component
public class ReadingFactory {

    private final AtomicInteger counter = new AtomicInteger();

    public WarpCoreReading createReading() {
        // Stardate: 78000.0 at 2026-01-01T00:00:00Z, one unit per hour after that.
        double stardate = Math.round((78000.0 + (Instant.now().getEpochSecond() - 1767225600L) / 3600.0) * 10.0) / 10.0;
        ThreadLocalRandom random = ThreadLocalRandom.current();
        return new WarpCoreReading(
                String.format(Locale.ROOT, "wc-%04d", counter.incrementAndGet()),
                stardate,
                random.nextInt(850, 951),
                random.nextInt(70, 101) / 100.0);
    }
}
