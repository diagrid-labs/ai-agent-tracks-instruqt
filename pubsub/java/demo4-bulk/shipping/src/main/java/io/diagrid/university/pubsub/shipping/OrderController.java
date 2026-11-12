package io.diagrid.university.pubsub.shipping;

import java.util.ArrayList;
import java.util.List;
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

    // The CloudEvents JSON format from the open CloudEvents SDK: each entry's "event" is one
    // CloudEvent in JSON.
    private static final EventFormat CLOUD_EVENTS =
            EventFormatProvider.getInstance().resolveFormat(JsonFormat.CONTENT_TYPE);

    // One status per entry. Record components are serialized in declaration order, so
    // "entryId" comes before "status".
    record EntryStatus(String entryId, String status) {
    }

    private final JsonMapper mapper;

    OrderController(JsonMapper mapper) {
        this.mapper = mapper;
    }

    // There is no Dapr code here: the route is wired only by resources/subscription-bulk.yaml,
    // and Dapr POSTs a batch of messages as one request. A String body accepts whatever
    // content type Dapr uses.
    @PostMapping("/orders/bulk")
    public ResponseEntity<Map<String, Object>> receiveBatch(@RequestBody(required = false) String body) {
        // The body is {"entries": [{"entryId", "event", ...}, ...], ...}: one entry per message.
        JsonNode entries = readEntries(body);
        if (entries == null) {
            // Not a bulk envelope at all: a non-2xx answer makes Dapr treat the delivery as failed.
            return ResponseEntity.badRequest().body(Map.of("error", "INVALID_BULK_REQUEST"));
        }
        List<String> ids = new ArrayList<>();
        List<EntryStatus> statuses = new ArrayList<>();
        for (JsonNode entry : entries) {
            // A missing or non-string entryId is answered as "".
            JsonNode entryIdNode = entry.path("entryId");
            String entryId = entryIdNode.isString() ? entryIdNode.asString() : "";
            String orderId = readOrderId(entry);
            if (orderId == null) {
                // DROP, not RETRY: a malformed entry will not parse any better on a redelivery.
                log.warn("shipping dropped unreadable entry {}", entryId);
                statuses.add(new EntryStatus(entryId, "DROP"));
            } else {
                ids.add(orderId);
                statuses.add(new EntryStatus(entryId, "SUCCESS"));
            }
        }
        log.info("shipping received batch of {} orders: {}", ids.size(), String.join(",", ids));
        // Bulk subscriptions are acknowledged per entry: Dapr redelivers only the entries that
        // are not SUCCESS.
        return ResponseEntity.ok(Map.of("statuses", statuses));
    }

    // Returns the "entries" array, or null if the body is not a bulk envelope.
    private JsonNode readEntries(String body) {
        if (body == null) {
            return null;
        }
        try {
            JsonNode entries = mapper.readTree(body).path("entries");
            return entries.isArray() ? entries : null;
        } catch (JacksonException e) {
            return null;
        }
    }

    // Returns entry.event.data.orderId, or null if the entry is unreadable.
    private String readOrderId(JsonNode entry) {
        // "event" is the CloudEvent; depending on the content type it is an object or a JSON string.
        JsonNode event = entry.path("event");
        try {
            // The event must be exactly one JSON object. The app's mapper rejects anything after the
            // JSON value, which the CloudEvents SDK would ignore, and `null` is not an object (the
            // SDK would turn it into no event at all).
            JsonNode json = event.isString() ? mapper.readTree(event.asString()) : event;
            if (!json.isObject()) {
                return null;
            }
            // Dapr delivers standard CloudEvents, so the open CloudEvents SDK can read each one
            // with no Dapr dependency.
            CloudEvent cloudEvent = CLOUD_EVENTS.deserialize(mapper.writeValueAsBytes(json));
            // The order is in the event's data. Only JSON data is read: data with a non-JSON
            // content type, or sent as data_base64, comes back from the SDK as plain bytes.
            if (!(cloudEvent.getData() instanceof JsonCloudEventData data)) {
                return null;
            }
            JsonNode orderId = mapper.readTree(data.toBytes()).path("orderId");
            return orderId.isString() ? orderId.asString() : null;
        } catch (EventDeserializationException | JacksonException e) {
            return null;
        }
    }
}
