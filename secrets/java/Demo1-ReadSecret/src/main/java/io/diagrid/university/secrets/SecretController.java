package io.diagrid.university.secrets;

import java.util.LinkedHashMap;
import java.util.Map;

import io.dapr.client.DaprClient;
import io.dapr.client.DaprClientBuilder;
import io.dapr.exceptions.DaprException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SecretController {

    private static final String SECRET_STORE = "secretstore";

    private final DaprClient daprClient = new DaprClientBuilder().build();

    @GetMapping("/secret/{name}")
    public ResponseEntity<Map<String, String>> getSecret(@PathVariable String name) {
        try {
            // The app only knows the secret store's name, never where the secrets really live.
            Map<String, String> secret = daprClient.getSecret(SECRET_STORE, name).block();
            if (secret == null || !secret.containsKey(name)) {
                return respond(HttpStatus.INTERNAL_SERVER_ERROR, name, "error", "INTERNAL");
            }
            return respond(HttpStatus.OK, name, "value", secret.get(name));
        } catch (DaprException e) {
            // Show the failure instead of hiding it: a refusal by Dapr (for example by secret
            // scoping) is a 403 with the gRPC status name, anything else is a 500. The SDK
            // message starts with the gRPC status ("PERMISSION_DENIED: ..."); use contains
            // rather than startsWith in case the message gets wrapped.
            if (e.getMessage() != null && e.getMessage().contains("PERMISSION_DENIED")) {
                return respond(HttpStatus.FORBIDDEN, name, "error", "PERMISSION_DENIED");
            }
            return respond(HttpStatus.INTERNAL_SERVER_ERROR, name, "error", "INTERNAL");
        }
    }

    // LinkedHashMap keeps "name" first in the JSON, matching the other languages.
    private static ResponseEntity<Map<String, String>> respond(
            HttpStatus status, String name, String key, String text) {
        Map<String, String> body = new LinkedHashMap<>();
        body.put("name", name);
        body.put(key, text);
        return ResponseEntity.status(status).body(body);
    }
}
