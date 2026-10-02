package io.diagrid.quickstart.bindings.venuebookings;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
public class BookingsController {

    private final BookingsService bookingsService;

    public BookingsController(BookingsService bookingsService) {
        this.bookingsService = bookingsService;
    }

    @PostMapping("/bookings")
    public Map<String, Object> createBooking(@RequestBody BookingRequest request) throws Exception {
        bookingsService.saveBooking(request.venue(), request.eventDate());
        return Map.of("status", "saved");
    }

    @GetMapping("/bookings")
    public Map<String, Object> listBookings() throws Exception {
        List<Booking> bookings = bookingsService.listBookings();
        return Map.of("bookings", bookings);
    }
}
