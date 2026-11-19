package io.diagrid.university.bindings.engineering;

import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EngineeringApplication {

    public static void main(String[] args) {
        SpringApplication.run(EngineeringApplication.class, args);
    }

    // One long-lived Dapr client per app. It holds the connection to the sidecar; DaprClient is
    // AutoCloseable, so Spring closes it on shutdown.
    @Bean
    DaprClient daprClient() {
        return new DaprClientBuilder().build();
    }
}
