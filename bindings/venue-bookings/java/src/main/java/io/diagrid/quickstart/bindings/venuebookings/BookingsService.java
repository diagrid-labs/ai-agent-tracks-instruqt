package io.diagrid.quickstart.bindings.venuebookings;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;
import io.dapr.client.DaprClient;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Service
public class BookingsService {
    private static final String BINDING_NAME = "postgres-binding";
    private final DaprClient daprClient;
    private final JsonMapper objectMapper;

    public BookingsService(DaprClient daprClient, JsonMapper objectMapper) {
        this.daprClient = daprClient;
        this.objectMapper = objectMapper;
    }

    public void saveBooking(String venue, String eventDate) {
        Map<String, String> metadata = Map.of(
                "sql", "INSERT INTO bookings (venue, event_date) VALUES ($1, $2)",
                "params", objectMapper.writeValueAsString(new String[] { venue, eventDate }));
        daprClient.invokeBinding(BINDING_NAME, "exec", new byte[0], metadata).block();
    }

    public List<Booking> listBookings() {
        Map<String, String> metadata = Map.of(
                "sql", "SELECT id, venue, event_date::text FROM bookings ORDER BY id",
                "params", "[]");
        byte[] response = daprClient.invokeBinding(BINDING_NAME, "query", new byte[0], metadata).block();
        if (response == null || response.length == 0) {
            return List.of();
        }
        List<List<Object>> rows = objectMapper.readValue(response, new TypeReference<List<List<Object>>>() {});
        return rows.stream()
                .map(row -> new Booking(((Number) row.get(0)).intValue(), (String) row.get(1), (String) row.get(2)))
                .toList();
    }
}
