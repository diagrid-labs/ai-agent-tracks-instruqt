package io.diagrid.quickstart.bindings.venuebookings;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingsController {
    private final BookingsService bookingsService;

    public BookingsController(BookingsService bookingsService) {
        this.bookingsService = bookingsService;
    }

    @PostMapping
    public SaveBookingResponse createBooking(@RequestBody BookingRequest request) {
        bookingsService.saveBooking(request.venue(), request.eventDate());
        return new SaveBookingResponse("saved");
    }

    @GetMapping
    public BookingsResponse listBookings() {
        return new BookingsResponse(bookingsService.listBookings());
    }
}
