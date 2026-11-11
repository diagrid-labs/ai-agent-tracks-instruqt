package io.diagrid.university.pubsub.orderapi;

import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import io.dapr.exceptions.DaprException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);
    private static final String PUBSUB = "pubsub";
    private static final String TOPIC = "orders";

    private final DaprClient daprClient = new DaprClientBuilder().build();
    private final ObjectMapper mapper = new ObjectMapper();

    @PostMapping("/orders")
    public ResponseEntity<Map<String, Object>> publishOrder(@RequestBody(required = false) String body) {
        Order order = readOrder(body);
        if (order == null) {
            return respond(HttpStatus.BAD_REQUEST, "error", "INVALID_ORDER");
        }
        try {
            // The app only knows the pub/sub component's name and the topic, never the broker
            // behind them. Dapr wraps the order in a CloudEvent and sends it to every subscriber.
            daprClient.publishEvent(PUBSUB, TOPIC, order).block();
        } catch (DaprException e) {
            return failure(e, order.orderId());
        }
        log.info("order-api published {} to {}", order.orderId(), TOPIC);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("orderId", order.orderId());
        result.put("topic", TOPIC);
        return ResponseEntity.ok(result);
    }

    // Show the failure instead of hiding it: the SDK message starts with the gRPC status
    // name ("NOT_FOUND: ..."). Use contains rather than startsWith in case the message gets
    // wrapped, and fall back to INTERNAL for anything unknown.
    private static ResponseEntity<Map<String, Object>> failure(DaprException e, String orderId) {
        String message = e.getMessage() == null ? "" : e.getMessage();
        String error = "INTERNAL";
        for (String name : new String[] {"NOT_FOUND", "PERMISSION_DENIED", "INVALID_ARGUMENT", "UNAVAILABLE"}) {
            if (message.contains(name)) {
                error = name;
                break;
            }
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("orderId", orderId);
        body.put("error", error);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
    }

    private static ResponseEntity<Map<String, Object>> respond(HttpStatus status, String key, String text) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put(key, text);
        return ResponseEntity.status(status).body(body);
    }

    // Returns null unless the body is a JSON object with all four Order fields.
    private Order readOrder(String body) {
        try {
            JsonNode root = mapper.readTree(body);
            if (root == null || !root.isObject()
                    || !root.path("orderId").isTextual()
                    || !root.path("item").isTextual()
                    || !root.path("quantity").isInt()
                    || !root.path("priority").isTextual()) {
                return null;
            }
            return new Order(root.get("orderId").asText(), root.get("item").asText(),
                    root.get("quantity").asInt(), root.get("priority").asText());
        } catch (Exception e) {
            return null;
        }
    }
}
