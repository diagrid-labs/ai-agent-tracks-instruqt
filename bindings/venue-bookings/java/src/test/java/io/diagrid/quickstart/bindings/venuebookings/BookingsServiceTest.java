package io.diagrid.quickstart.bindings.venuebookings;

import io.dapr.client.DaprClient;
import tools.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for BookingsService, with DaprClient mocked out. These don't need a running
 * Dapr sidecar or Postgres: they only assert that each method calls the binding with the
 * right operation and SQL, and parses the response the way the binding actually shapes it.
 */
class BookingsServiceTest {

    @Test
    @SuppressWarnings("unchecked")
    void saveBooking_usesExecOperation() throws Exception {
        DaprClient daprClient = mock(DaprClient.class);
        when(daprClient.invokeBinding(anyString(), anyString(), any(byte[].class), anyMap()))
                .thenReturn(Mono.just("[]".getBytes(StandardCharsets.UTF_8)));

        BookingsService service = new BookingsService(daprClient, JsonMapper.builder().build());
        service.saveBooking("Grand Ballroom", "2026-03-15");

        ArgumentCaptor<String> operationCaptor = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<Map<String, String>> metadataCaptor = ArgumentCaptor.forClass(Map.class);
        verify(daprClient).invokeBinding(
                eq("postgres-binding"), operationCaptor.capture(), any(byte[].class), metadataCaptor.capture());

        assertEquals("exec", operationCaptor.getValue());
        assertTrue(metadataCaptor.getValue().get("sql").contains("INSERT INTO bookings"));
        assertTrue(metadataCaptor.getValue().get("params").contains("Grand Ballroom"));
    }

    @Test
    void listBookings_usesQueryOperation() throws Exception {
        DaprClient daprClient = mock(DaprClient.class);
        byte[] response = "[[1,\"Grand Ballroom\",\"2026-03-15\"]]".getBytes(StandardCharsets.UTF_8);
        when(daprClient.invokeBinding(anyString(), anyString(), any(byte[].class), anyMap()))
                .thenReturn(Mono.just(response));

        BookingsService service = new BookingsService(daprClient, JsonMapper.builder().build());
        List<Booking> bookings = service.listBookings();

        assertEquals(1, bookings.size());
        assertEquals("Grand Ballroom", bookings.get(0).venue());
        assertEquals("2026-03-15", bookings.get(0).eventDate());

        ArgumentCaptor<String> operationCaptor = ArgumentCaptor.forClass(String.class);
        verify(daprClient).invokeBinding(eq("postgres-binding"), operationCaptor.capture(), any(byte[].class), anyMap());
        assertEquals("query", operationCaptor.getValue());
        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> metadata = ArgumentCaptor.forClass(Map.class);
        verify(daprClient).invokeBinding(eq("postgres-binding"), eq("query"), any(byte[].class), metadata.capture());
        assertEquals("SELECT id, venue, event_date::text FROM bookings ORDER BY id", metadata.getValue().get("sql"));
    }

    @Test
    void listBookings_handlesEmptyResult() throws Exception {
        DaprClient daprClient = mock(DaprClient.class);
        when(daprClient.invokeBinding(anyString(), anyString(), any(byte[].class), anyMap()))
                .thenReturn(Mono.just("[]".getBytes(StandardCharsets.UTF_8)));

        BookingsService service = new BookingsService(daprClient, JsonMapper.builder().build());
        List<Booking> bookings = service.listBookings();

        assertTrue(bookings.isEmpty());
    }
}
