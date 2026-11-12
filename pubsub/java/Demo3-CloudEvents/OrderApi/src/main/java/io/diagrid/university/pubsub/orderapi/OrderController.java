package io.diagrid.university.pubsub.orderapi;

import java.util.Map;

import io.dapr.client.DaprClient;
import io.dapr.exceptions.DaprException;
import io.grpc.StatusRuntimeException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
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
    private static final String PUBSUB = "pubsub";
    private static final String TOPIC = "orders";
    private static final String RAW_TOPIC = "orders-raw";

    // Response bodies. Record components are serialized in declaration order, so the JSON
    // keys come out in the contract's order.
    record Published(String orderId, String topic) {
    }

    record PublishFailed(String orderId, String error) {
    }

    private final DaprClient daprClient;
    private final JsonMapper mapper;

    // The DaprClient bean is declared in OrderApiApplication; the JsonMapper is Spring Boot's.
    OrderController(DaprClient daprClient, JsonMapper mapper) {
        this.daprClient = daprClient;
        this.mapper = mapper;
    }

    // Dapr wraps the order in a CloudEvent: an envelope with id, source, type and the order in "data".
    @PostMapping("/orders")
    public ResponseEntity<?> publishOrder(@RequestBody(required = false) String body) {
        return publish(body, TOPIC, Map.of());
    }

    // The rawPayload publish metadata tells Dapr not to add the envelope: the order itself is
    // the message on the topic. The subscription needs no rawPayload of its own (see subscription-orders-raw.yaml).
    @PostMapping("/orders/raw")
    public ResponseEntity<?> publishRawOrder(@RequestBody(required = false) String body) {
        return publish(body, RAW_TOPIC, Map.of("rawPayload", "true"));
    }

    private ResponseEntity<?> publish(String body, String topic, Map<String, String> metadata) {
        Order order = readOrder(body);
        if (order == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "INVALID_ORDER"));
        }
        try {
            // The app only knows the pub/sub component's name and the topic, never the broker
            // behind them.
            daprClient.publishEvent(PUBSUB, topic, order, metadata).block();
        } catch (DaprException e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new PublishFailed(order.orderId(), errorName(e)));
        }
        log.info("order-api published {} to {}", order.orderId(), topic);
        return ResponseEntity.ok(new Published(order.orderId(), topic));
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
