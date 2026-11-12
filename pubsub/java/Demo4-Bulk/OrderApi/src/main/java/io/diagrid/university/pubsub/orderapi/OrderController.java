package io.diagrid.university.pubsub.orderapi;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import io.dapr.client.DaprClient;
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
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);
    private static final String PUBSUB = "pubsub";
    private static final String TOPIC = "orders";

    // Response bodies. Record components are serialized in declaration order, so the JSON
    // keys come out in the contract's order.
    record Published(String orderId, String topic) {
    }

    record PublishFailed(String orderId, String error) {
    }

    record BulkPublished(int sent, int failed) {
    }

    private final DaprClient daprClient;
    private final JsonMapper mapper;

    // The DaprClient bean is declared in OrderApiApplication; the JsonMapper is Spring Boot's.
    OrderController(DaprClient daprClient, JsonMapper mapper) {
        this.daprClient = daprClient;
        this.mapper = mapper;
    }

    @PostMapping("/orders")
    public ResponseEntity<?> publishOrder(@RequestBody(required = false) String body) {
        Order order = readOrder(body);
        if (order == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "INVALID_ORDER"));
        }
        try {
            // The app only knows the pub/sub component's name and the topic, never the broker
            // behind them. Dapr wraps the order in a CloudEvent and sends it to every subscriber.
            daprClient.publishEvent(PUBSUB, TOPIC, order).block();
        } catch (DaprException e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new PublishFailed(order.orderId(), errorName(e)));
        }
        log.info("order-api published {} to {}", order.orderId(), TOPIC);
        return ResponseEntity.ok(new Published(order.orderId(), TOPIC));
    }

    @PostMapping("/orders/bulk")
    public ResponseEntity<?> publishBulk(
            @RequestParam(required = false) String count,
            @RequestParam(defaultValue = "o") String prefix) {
        int n = parseCount(count);
        if (n < 1 || n > 100) {
            return ResponseEntity.badRequest().body(Map.of("error", "INVALID_COUNT"));
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
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("error", errorName(e)));
        }
        if (response == null) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("error", "INTERNAL"));
        }
        int failed = response.getFailedEntries().size();
        log.info("order-api bulk published {} orders to {}, {} failed", n, TOPIC, failed);
        return ResponseEntity.ok(new BulkPublished(n, failed));
    }

    // count must be a whole number from 1 to 100 in plain ASCII digits (Integer.parseInt alone
    // would also take "+5"); surrounding whitespace is ignored. Returns 0 when it is not a number.
    private static int parseCount(String count) {
        String digits = count == null ? "" : count.strip();
        if (!digits.matches("[0-9]+")) {
            return 0;
        }
        try {
            return Integer.parseInt(digits);
        } catch (NumberFormatException e) {
            return 0; // more digits than an int holds
        }
    }

    // Show the failure instead of hiding it: when Dapr rejects the publish, the DaprException
    // carries the sidecar's gRPC StatusRuntimeException in its cause chain, and that status
    // code's name ("NOT_FOUND") is the same name the other languages report. INTERNAL when
    // there is no gRPC status.
    private static String errorName(DaprException e) {
        for (Throwable cause = e.getCause(); cause != null; cause = cause.getCause()) {
            if (cause instanceof StatusRuntimeException grpc) {
                return grpc.getStatus().getCode().name();
            }
        }
        return "INTERNAL";
    }

    // Returns null unless the body is exactly one JSON object with all four Order fields.
    // Validation is by hand on purpose: binding to Order directly would let Jackson coerce
    // types (a string "2" as the quantity, for example). Jackson 3 also rejects anything after
    // the JSON value (FAIL_ON_TRAILING_TOKENS is on by default), so "{...} x" is invalid too.
    private Order readOrder(String body) {
        if (body == null) {
            return null;
        }
        JsonNode root;
        try {
            root = mapper.readTree(body);
        } catch (JacksonException e) {
            return null;
        }
        if (!root.isObject()
                || !root.path("orderId").isString()
                || !root.path("item").isString()
                || !root.path("quantity").isInt()
                || !root.path("priority").isString()) {
            return null;
        }
        return new Order(root.get("orderId").asString(), root.get("item").asString(),
                root.get("quantity").asInt(), root.get("priority").asString());
    }
}
