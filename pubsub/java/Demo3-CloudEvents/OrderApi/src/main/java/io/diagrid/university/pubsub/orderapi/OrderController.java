package io.diagrid.university.pubsub.orderapi;

import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import io.dapr.exceptions.DaprException;
import io.grpc.StatusRuntimeException;
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

    private final DaprClient daprClient = new DaprClientBuilder().build();
    private final ObjectMapper mapper = new ObjectMapper();

    // Dapr wraps the order in a CloudEvent: an envelope with id, source, type and the order in "data".
    @PostMapping("/orders")
    public ResponseEntity<Map<String, Object>> publishOrder(@RequestBody(required = false) String body) {
        return publish(body, "orders", null);
    }

    // The rawPayload publish metadata tells Dapr not to add the envelope: the order itself is
    // the message on the topic. The subscriber has to expect the same (see subscription-orders-raw.yaml).
    @PostMapping("/orders/raw")
    public ResponseEntity<Map<String, Object>> publishRawOrder(@RequestBody(required = false) String body) {
        return publish(body, "orders-raw", Map.of("rawPayload", "true"));
    }

    private ResponseEntity<Map<String, Object>> publish(String body, String topic, Map<String, String> metadata) {
        Order order = readOrder(body);
        if (order == null) {
            return respond(HttpStatus.BAD_REQUEST, "error", "INVALID_ORDER");
        }
        try {
            // The app only knows the pub/sub component's name and the topic, never the broker
            // behind them.
            if (metadata == null) {
                daprClient.publishEvent(PUBSUB, topic, order).block();
            } else {
                daprClient.publishEvent(PUBSUB, topic, order, metadata).block();
            }
        } catch (DaprException e) {
            return failure(e, order.orderId());
        }
        log.info("order-api published {} to {}", order.orderId(), topic);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("orderId", order.orderId());
        result.put("topic", topic);
        return ResponseEntity.ok(result);
    }

    // Show the failure instead of hiding it: the DaprException wraps a gRPC
    // StatusRuntimeException, whose status code name ("NOT_FOUND") is the same name the
    // other languages report. INTERNAL only when no gRPC status is in the cause chain.
    private static ResponseEntity<Map<String, Object>> failure(DaprException e, String orderId) {
        String error = "INTERNAL";
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof StatusRuntimeException grpc) {
                error = grpc.getStatus().getCode().name();
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
