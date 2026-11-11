package io.diagrid.university.pubsub.shipping;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);
    private final ObjectMapper mapper = new ObjectMapper();

    // There is no Dapr code here: the route is wired only by resources/subscription-bulk.yaml,
    // and Dapr POSTs a batch of messages as one request. A String body accepts whatever
    // content type Dapr uses.
    @PostMapping("/orders/bulk")
    public ResponseEntity<Map<String, Object>> receiveBatch(@RequestBody(required = false) String body) {
        // The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
        JsonNode entries;
        try {
            entries = mapper.readTree(body).path("entries");
        } catch (Exception e) {
            entries = null;
        }
        if (entries == null || !entries.isArray()) {
            // Not a bulk envelope at all: a non-2xx answer makes Dapr treat the delivery as failed.
            return ResponseEntity.badRequest().body(Map.of("error", "INVALID_BULK_REQUEST"));
        }
        List<String> ids = new ArrayList<>();
        List<Map<String, String>> statuses = new ArrayList<>();
        for (JsonNode entry : entries) {
            String entryId = entry.path("entryId").asString("");
            String orderId = readOrderId(entry);
            Map<String, String> status = new LinkedHashMap<>();
            status.put("entryId", entryId);
            if (orderId == null) {
                // DROP, not RETRY: a malformed entry will not parse any better on a redelivery.
                log.info("shipping dropped unreadable entry {}", entryId);
                status.put("status", "DROP");
            } else {
                ids.add(orderId);
                status.put("status", "SUCCESS");
            }
            statuses.add(status);
        }
        log.info("shipping received batch of {} orders: {}", ids.size(), String.join(",", ids));
        // Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
        // are not SUCCESS.
        return ResponseEntity.ok(Map.of("statuses", statuses));
    }

    // Returns entry.event.data.orderId, or null if the entry is unreadable.
    private String readOrderId(JsonNode entry) {
        try {
            JsonNode event = entry.path("event");
            // "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
            if (event.isString()) {
                event = mapper.readTree(event.asString());
            }
            JsonNode orderId = event.path("data").path("orderId");
            return orderId.isString() ? orderId.asString() : null;
        } catch (Exception e) {
            return null;
        }
    }
}
