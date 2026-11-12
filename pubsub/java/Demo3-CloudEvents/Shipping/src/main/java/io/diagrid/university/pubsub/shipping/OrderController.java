package io.diagrid.university.pubsub.shipping;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Objects;

import io.cloudevents.CloudEvent;
import io.cloudevents.core.format.EventDeserializationException;
import io.cloudevents.core.format.EventFormat;
import io.cloudevents.core.provider.EventFormatProvider;
import io.cloudevents.jackson.JsonFormat;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.core.JacksonException;
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

    // There is no Dapr code here: both routes log exactly the body Dapr sends. The
    // subscriptions live in resources/*.yaml. Dapr sends the envelope as
    // application/cloudevents+json; a String body accepts that as well as application/json.

    // /orders is a normal subscription: the body is a CloudEvent envelope with the order in "data".
    @PostMapping("/orders")
    public ResponseEntity<Map<String, String>> receiveOrder(@RequestBody(required = false) String body) {
        // Spring passes null for an empty body; log it as an empty string.
        log.info("shipping received with envelope: {}", Objects.toString(body, ""));
        if (body != null) {
            try {
                // The CloudEvents SDK stops after the first JSON value and turns a body of `null`
                // into no event at all. The app's mapper rejects anything after the JSON value, so
                // only a body that is exactly one JSON object goes to the SDK.
                if (mapper.readTree(body).isObject()) {
                    // Dapr delivers a standard CloudEvent, so the open CloudEvents SDK can read it
                    // with no Dapr dependency.
                    CloudEvent event = CLOUD_EVENTS.deserialize(body.getBytes(StandardCharsets.UTF_8));
                    log.info("shipping parsed CloudEvent id={} type={} source={}",
                            event.getId(), event.getType(), event.getSource());
                }
            } catch (EventDeserializationException | JacksonException e) {
                // Not a CloudEvent: the raw line above already shows what arrived.
            }
        }
        // SUCCESS tells Dapr the message is handled, so it is not redelivered.
        return ResponseEntity.ok(Map.of("status", "SUCCESS"));
    }

    // /orders-raw receives what the publisher put on the topic: the order itself, no envelope.
    // It is not a CloudEvent, so there is nothing for the CloudEvents SDK to read.
    @PostMapping("/orders-raw")
    public ResponseEntity<Map<String, String>> receiveRawOrder(@RequestBody(required = false) String body) {
        log.info("shipping received raw: {}", Objects.toString(body, ""));
        return ResponseEntity.ok(Map.of("status", "SUCCESS"));
    }
}
