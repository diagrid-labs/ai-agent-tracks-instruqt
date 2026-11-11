package io.diagrid.university.pubsub.shipping;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
    public Map<String, Object> receiveBatch(@RequestBody String body) throws Exception {
        // The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
        List<String> ids = new ArrayList<>();
        List<Map<String, String>> statuses = new ArrayList<>();
        for (JsonNode entry : mapper.readTree(body).path("entries")) {
            JsonNode event = entry.path("event");
            // "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
            if (event.isString()) {
                event = mapper.readTree(event.asString());
            }
            ids.add(event.path("data").path("orderId").asString());
            Map<String, String> status = new LinkedHashMap<>();
            status.put("entryId", entry.path("entryId").asString());
            status.put("status", "SUCCESS");
            statuses.add(status);
        }
        log.info("shipping received batch of {} orders: {}", ids.size(), String.join(",", ids));
        // Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
        // are not SUCCESS.
        return Map.of("statuses", statuses);
    }
}
