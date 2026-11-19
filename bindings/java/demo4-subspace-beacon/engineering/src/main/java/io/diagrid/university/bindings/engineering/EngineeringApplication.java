package io.diagrid.university.bindings.engineering;

import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

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

    // Service invocation client. Every request goes to our own Dapr sidecar (dapr run sets
    // DAPR_HTTP_PORT), and the dapr-app-id header tells the sidecar which app to forward it to.
    // There is no host or port of the beacon anywhere in this code.
    @Bean
    RestClient beaconClient(RestClient.Builder builder, @Value("${DAPR_HTTP_PORT:3520}") int daprHttpPort) {
        return builder
                .baseUrl("http://localhost:" + daprHttpPort)
                .defaultHeader("dapr-app-id", "subspace-beacon")
                .build();
    }
}
