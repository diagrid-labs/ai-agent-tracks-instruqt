package io.diagrid.quickstart.bindings.venuebookings;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.dapr.client.DaprClient;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Saves and queries venue bookings through a single Dapr output binding to PostgreSQL.
 *
 * <p>There is only one binding here, bindings.postgresql, which is output-only. Dapr has no
 * "input binding" for Postgres: an input binding is something that triggers your app (like
 * a Cron schedule), and Postgres has no mechanism for that. Both methods below call the
 * same binding, just with a different operation.
 *
 * <p>Note: unlike the Python and .NET Dapr SDKs, the Java SDK's invokeBinding does not expose
 * response metadata (e.g. "rows-affected") alongside the payload, so saveBooking here only
 * confirms the write went through, it can't report how many rows were affected.
 */
@Service
public class BookingsService {

    private static final String BINDING_NAME = "postgres-binding";

    private final DaprClient daprClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public BookingsService(DaprClient daprClient) {
        this.daprClient = daprClient;
    }

    /** Save a booking with the binding's "exec" operation (an INSERT). */
    public void saveBooking(String venue, String eventDate) throws Exception {
        Map<String, String> metadata = new HashMap<>();
        metadata.put("sql", "INSERT INTO bookings (venue, event_date) VALUES ($1, $2)");
        metadata.put("params", objectMapper.writeValueAsString(new String[] { venue, eventDate }));
        daprClient.invokeBinding(BINDING_NAME, "exec", new byte[0], metadata).block();
    }

    /** Read every booking back with the same binding's "query" operation (a SELECT). */
    public List<Booking> listBookings() throws Exception {
        Map<String, String> metadata = new HashMap<>();
        metadata.put("sql", "SELECT id, venue, event_date FROM bookings ORDER BY id");
        metadata.put("params", "[]");
        byte[] response = daprClient.invokeBinding(BINDING_NAME, "query", new byte[0], metadata).block();
        if (response == null || response.length == 0) {
            return List.of();
        }
        List<List<Object>> rows = objectMapper.readValue(response, new TypeReference<List<List<Object>>>() {
        });
        return rows.stream()
                .map(row -> new Booking(((Number) row.get(0)).intValue(), (String) row.get(1), (String) row.get(2)))
                .collect(Collectors.toList());
    }
}
