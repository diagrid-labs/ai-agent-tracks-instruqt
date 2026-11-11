package io.diagrid.university.pubsub.shipping;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);

    // There is no Dapr code here: both routes log exactly the body Dapr sends. The
    // subscriptions live in resources/*.yaml. Dapr sends the envelope as
    // application/cloudevents+json; a String body accepts that as well as application/json.

    // /orders is a normal subscription: the body is a CloudEvent envelope with the order in "data".
    @PostMapping("/orders")
    public Map<String, String> receiveOrder(@RequestBody String body) {
        log.info("shipping received with envelope: {}", body);
        // SUCCESS tells Dapr the message is handled, so it is not redelivered.
        return Map.of("status", "SUCCESS");
    }

    // /orders-raw receives what the publisher put on the topic: the order itself, no envelope.
    @PostMapping("/orders-raw")
    public Map<String, String> receiveRawOrder(@RequestBody String body) {
        log.info("shipping received raw: {}", body);
        return Map.of("status", "SUCCESS");
    }
}
