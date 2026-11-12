package io.diagrid.university.pubsub.invoicing;

import java.util.Map;

import io.dapr.Topic;
import io.dapr.client.domain.CloudEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);

    // The subscription lives in code: @Topic makes the Dapr SDK answer /dapr/subscribe, the
    // endpoint Dapr calls at startup to learn this app's subscriptions. That is what makes
    // the subscription programmatic.
    @Topic(name = "orders", pubsubName = "pubsub")
    @PostMapping("/orders")
    public ResponseEntity<Map<String, String>> receiveOrder(@RequestBody CloudEvent<Order> event) {
        log.info("invoicing received order {}", event.getData().orderId());
        // SUCCESS tells Dapr the message is handled, so it is not redelivered.
        return ResponseEntity.ok(Map.of("status", "SUCCESS"));
    }
}
