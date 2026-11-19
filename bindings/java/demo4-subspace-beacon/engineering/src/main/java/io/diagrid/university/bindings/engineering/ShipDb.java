package io.diagrid.university.bindings.engineering;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import io.dapr.client.DaprClient;
import io.dapr.client.domain.InvokeBindingRequest;
import io.dapr.utils.TypeRef;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

// Thin wrapper around the ship-db output binding. The app only knows the component name
// "ship-db", never that PostgreSQL is behind it.
@Component
public class ShipDb {

    // The SQL the engineering app runs. Every value goes through $1, $2... placeholders, never
    // through string concatenation.
    public static final String CLEAR_COMMS = "DELETE FROM comms_log";

    public static final String INSERT_PING =
            "INSERT INTO comms_log (beacon_id, signal_strength, message, stardate) VALUES ($1, $2, $3, $4)";

    public static final String LAST_PINGS = "SELECT signal_strength FROM comms_log ORDER BY id DESC LIMIT 3";

    private static final String BINDING = "ship-db";

    private final DaprClient daprClient;
    private final JsonMapper mapper;

    ShipDb(DaprClient daprClient, JsonMapper mapper) {
        this.daprClient = daprClient;
        this.mapper = mapper;
    }

    // "exec" runs a statement that changes data (INSERT, DELETE) and returns no rows.
    public Mono<Void> exec(String sql, Object... args) {
        return daprClient.invokeBinding(request("exec", sql, args));
    }

    // "query" runs a SELECT. The binding answers with a JSON array of arrays: one inner list per
    // row, values in the order of the SELECT list, so callers read them by position.
    public List<List<Object>> query(String sql, Object... args) {
        byte[] data = daprClient.invokeBinding(request("query", sql, args), TypeRef.BYTE_ARRAY).block();
        return mapper.readValue(data, new TypeReference<List<List<Object>>>() { });
    }

    private InvokeBindingRequest request(String operation, String sql, Object[] args) {
        // The binding name and the operation say where and what; the SQL and its parameters
        // travel as request metadata. "params" is a JSON array in a string, matching $1, $2...
        Map<String, String> metadata = new HashMap<>();
        metadata.put("sql", sql);
        if (args.length > 0) {
            metadata.put("params", mapper.writeValueAsString(args));
        }
        return new InvokeBindingRequest(BINDING, operation).setMetadata(metadata);
    }
}
