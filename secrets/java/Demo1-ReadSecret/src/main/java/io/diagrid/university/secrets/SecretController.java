package io.diagrid.university.secrets;

import java.util.LinkedHashMap;
import java.util.Map;

import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SecretController {

    private static final String SECRET_STORE = "secretstore";

    private final DaprClient daprClient = new DaprClientBuilder().build();

    @GetMapping("/secret/{name}")
    public Map<String, String> getSecret(@PathVariable String name) {
        // The app only knows the secret store's name, never where the secrets really live.
        Map<String, String> secret = daprClient.getSecret(SECRET_STORE, name).block();
        // LinkedHashMap keeps "name" before "value" in the JSON, matching the other languages.
        Map<String, String> response = new LinkedHashMap<>();
        response.put("name", name);
        response.put("value", secret.get(name));
        return response;
    }
}
