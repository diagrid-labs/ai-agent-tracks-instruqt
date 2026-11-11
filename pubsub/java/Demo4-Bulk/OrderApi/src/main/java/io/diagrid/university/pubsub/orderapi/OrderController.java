package io.diagrid.university.pubsub.orderapi;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import io.dapr.client.domain.BulkPublishResponse;
import io.dapr.exceptions.DaprException;
import io.grpc.StatusRuntimeException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
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

    @PostMapping("/orders/bulk")
    public ResponseEntity<Map<String, Object>> publishBulk(
            @RequestParam(required = false) String count,
            @RequestParam(defaultValue = "o") String prefix) {
        // count must be a whole number from 1 to 100.
        int n;
        try {
            n = Integer.parseInt(count);
        } catch (NumberFormatException e) {
            n = 0;
        }
        if (n < 1 || n > 100) {
            return respond(HttpStatus.BAD_REQUEST, "error", "INVALID_COUNT");
        }
        List<Order> orders = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            orders.add(new Order(prefix + "-" + i, "coffee-beans", 1, "standard"));
        }
        BulkPublishResponse<Order> response;
        try {
            // One call publishes all orders. Dapr still wraps each one in its own CloudEvent.
            // A bulk publish can succeed for some entries and fail for others, so the response
            // lists the entries that failed instead of throwing for them.
            response = daprClient.publishEvents(PUBSUB, TOPIC, "application/json", orders).block();
        } catch (DaprException e) {
            // There is no single order to name here, so the error body has no orderId.
            return failure(e, null);
        }
        int failed = response.getFailedEntries().size();
        log.info("order-api bulk published {} orders to {}, {} failed", n, TOPIC, failed);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("sent", n);
        result.put("failed", failed);
        return ResponseEntity.ok(result);
    }

    // Show the failure instead of hiding it: the DaprException wraps a gRPC
    // StatusRuntimeException, whose status code name ("NOT_FOUND") is the same name the
    // other languages report. INTERNAL only when no gRPC status is in the cause chain.
    private static String errorName(DaprException e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t instanceof StatusRuntimeException grpc) {
                return grpc.getStatus().getCode().name();
            }
        }
        return "INTERNAL";
    }

    private static ResponseEntity<Map<String, Object>> failure(DaprException e, String orderId) {
        Map<String, Object> body = new LinkedHashMap<>();
        if (orderId != null) {
            body.put("orderId", orderId);
        }
        body.put("error", errorName(e));
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
