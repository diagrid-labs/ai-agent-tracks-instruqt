package io.diagrid.university.pubsub.warehouse;

import io.dapr.client.DaprClientBuilder;
import io.dapr.client.DaprPreviewClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WarehouseApplication {

    public static void main(String[] args) {
        SpringApplication.run(WarehouseApplication.class, args);
    }

    // Streaming subscriptions live on the preview client. One long-lived client per app: it
    // holds the connection to the sidecar, and Spring closes it (it is AutoCloseable) on shutdown.
    @Bean
    DaprPreviewClient daprPreviewClient() {
        return new DaprClientBuilder().buildPreviewClient();
    }
}
