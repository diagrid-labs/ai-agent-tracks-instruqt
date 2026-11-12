package io.diagrid.university.pubsub.shipping;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);

    private final JsonMapper mapper;

    OrderController(JsonMapper mapper) {
        this.mapper = mapper;
    }

    // There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
    // Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
    @PostMapping("/orders")
    public ResponseEntity<Map<String, String>> receiveOrder(@RequestBody(required = false) String body) {
        String orderId = readOrderId(body);
        if (orderId == null) {
            // DROP, not an error status: Dapr redelivers on any non-2xx answer (except 404), and an
            // unreadable event will not parse any better on a redelivery.
            log.warn("shipping dropped unreadable event");
            return ResponseEntity.ok(Map.of("status", "DROP"));
        }
        log.info("shipping received order {}", orderId);
        // SUCCESS tells Dapr the message is handled, so it is not redelivered.
        return ResponseEntity.ok(Map.of("status", "SUCCESS"));
    }

    // Returns data.orderId from the CloudEvent body, or null if the event is unreadable.
    private String readOrderId(String body) {
        if (body == null) {
            return null;
        }
        try {
            // The order is in the CloudEvent's "data" field.
            JsonNode orderId = mapper.readTree(body).path("data").path("orderId");
            return orderId.isString() ? orderId.asString() : null;
        } catch (JacksonException e) {
            return null;
        }
    }
}
