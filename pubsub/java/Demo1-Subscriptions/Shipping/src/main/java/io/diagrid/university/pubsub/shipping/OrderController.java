package io.diagrid.university.pubsub.shipping;

import java.util.Map;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private static final Logger log = LoggerFactory.getLogger(OrderController.class);
    private final JsonMapper mapper = new JsonMapper();

    // There is no Dapr code here. The subscription lives in resources/subscription-shipping.yaml;
    // Dapr POSTs each message to this route as a CloudEvent, and the app just reads the JSON.
    @PostMapping("/orders")
    public Map<String, String> receiveOrder(@RequestBody String body) throws Exception {
        JsonNode event = mapper.readTree(body);
        // The order is in the CloudEvent's "data" field.
        log.info("shipping received order {}", event.path("data").path("orderId").asString());
        // SUCCESS tells Dapr the message is handled, so it is not redelivered.
        return Map.of("status", "SUCCESS");
    }
}
