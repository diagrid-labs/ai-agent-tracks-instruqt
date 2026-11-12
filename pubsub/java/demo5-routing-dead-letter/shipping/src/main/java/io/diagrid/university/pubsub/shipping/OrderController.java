package io.diagrid.university.pubsub.shipping;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import io.cloudevents.CloudEvent;
import io.cloudevents.core.format.EventDeserializationException;
import io.cloudevents.core.format.EventFormat;
import io.cloudevents.core.provider.EventFormatProvider;
import io.cloudevents.jackson.JsonCloudEventData;
import io.cloudevents.jackson.JsonFormat;
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

    // The CloudEvents JSON format from the open CloudEvents SDK. Dapr delivers in structured
    // mode: the whole CloudEvent is the JSON request body.
    private static final EventFormat CLOUD_EVENTS =
            EventFormatProvider.getInstance().resolveFormat(JsonFormat.CONTENT_TYPE);

    private final JsonMapper mapper;

    OrderController(JsonMapper mapper) {
        this.mapper = mapper;
    }

    // There is no Dapr code here. The routes are wired only by resources/subscription-orders.yaml
    // and resources/subscription-dead-letter.yaml: Dapr picks /orders/express or /orders/standard
    // from the order's priority, and POSTs dead-lettered messages to /orders/dead.
    @PostMapping("/orders/express")
    public ResponseEntity<Map<String, String>> express(@RequestBody(required = false) String body) {
        return handle(body, "express");
    }

    @PostMapping("/orders/standard")
    public ResponseEntity<Map<String, String>> standard(@RequestBody(required = false) String body) {
        return handle(body, "standard");
    }

    // Dapr forwards the original CloudEvent to orders-dead once the retries are used up,
    // so the order is in "data" here too.
    @PostMapping("/orders/dead")
    public ResponseEntity<Map<String, String>> deadLetter(@RequestBody(required = false) String body) {
        JsonNode data = readData(body);
        if (data == null) {
            return dropped();
        }
        log.info("shipping dead-lettered order {}", data.path("orderId").asString());
        return ResponseEntity.ok(Map.of("status", "SUCCESS"));
    }

    private ResponseEntity<Map<String, String>> handle(String body, String route) {
        JsonNode data = readData(body);
        if (data == null) {
            return dropped();
        }
        String orderId = data.path("orderId").asString();
        if ("poison".equals(data.path("item").asString(""))) {
            log.warn("shipping rejected order {}", orderId);
            // A 500 with RETRY makes Dapr redeliver per resources/resiliency.yaml, then dead-letter.
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(Map.of("status", "RETRY"));
        }
        log.info("shipping {} order {}", route, orderId);
        // SUCCESS tells Dapr the message is handled, so it is not redelivered.
        return ResponseEntity.ok(Map.of("status", "SUCCESS"));
    }

    // DROP, not RETRY: an event without an order id will not parse any better on a redelivery.
    private ResponseEntity<Map<String, String>> dropped() {
        log.warn("shipping dropped unreadable event");
        return ResponseEntity.ok(Map.of("status", "DROP"));
    }

    // Returns the CloudEvent's data, or null if the body is not a CloudEvent with a string
    // data.orderId.
    private JsonNode readData(String body) {
        if (body == null) {
            return null;
        }
        try {
            // The CloudEvents SDK stops after the first JSON value and turns a body of `null` into
            // no event at all. The app's mapper rejects anything after the JSON value, so this
            // check makes both of those unreadable: the body must be exactly one JSON object.
            if (!mapper.readTree(body).isObject()) {
                return null;
            }
            // Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it with no
            // Dapr dependency.
            CloudEvent event = CLOUD_EVENTS.deserialize(body.getBytes(StandardCharsets.UTF_8));
            // The order is in the event's data. Only JSON data is read: data with a non-JSON
            // content type, or sent as data_base64, comes back from the SDK as plain bytes.
            if (!(event.getData() instanceof JsonCloudEventData jsonData)) {
                return null;
            }
            JsonNode data = mapper.readTree(jsonData.toBytes());
            return data.path("orderId").isString() ? data : null;
        } catch (EventDeserializationException | JacksonException e) {
            return null;
        }
    }
}
