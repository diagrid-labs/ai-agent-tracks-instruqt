package io.diagrid.university.pubsub.orderapi;

import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }

    // One long-lived Dapr client per app, injected where it is needed. It holds the connection
    // to the sidecar; DaprClient is AutoCloseable, so Spring closes it on shutdown.
    @Bean
    DaprClient daprClient() {
        return new DaprClientBuilder().build();
    }
}
