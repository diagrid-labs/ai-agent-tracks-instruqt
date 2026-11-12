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

    // There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
    // Dapr POSTs each message to this route as a CloudEvent, and the app reads it with the
    // CloudEvents SDK.
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
            if (!(event.getData() instanceof JsonCloudEventData data)) {
                return null;
            }
            JsonNode orderId = mapper.readTree(data.toBytes()).path("orderId");
            return orderId.isString() ? orderId.asString() : null;
        } catch (EventDeserializationException | JacksonException e) {
            return null;
        }
    }
}
