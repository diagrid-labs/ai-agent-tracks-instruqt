package io.diagrid.university.bindings.engineering;

import java.util.Locale;

// One warp core reading. The component order is the JSON key order.
public record WarpCoreReading(String readingId, double stardate, int coreTempK, double plasmaFlow) {

    // Log lines use fixed decimals, so every language prints the same text.
    public String toLogLine() {
        return String.format(Locale.ROOT,
                "engineering warp-core scan %s stardate=%.1f coreTempK=%d plasmaFlow=%.2f",
                readingId, stardate, coreTempK, plasmaFlow);
    }
}
