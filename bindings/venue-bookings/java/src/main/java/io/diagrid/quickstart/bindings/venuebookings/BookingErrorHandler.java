package io.diagrid.quickstart.bindings.venuebookings;

import io.dapr.exceptions.DaprException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import tools.jackson.core.JacksonException;

@RestControllerAdvice
public class BookingErrorHandler {
    private static final Logger LOG = LoggerFactory.getLogger(BookingErrorHandler.class);

    @ExceptionHandler(DaprException.class)
    public ProblemDetail bindingFailed(DaprException error) {
        LOG.error("Postgres binding request failed", error);
        return ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE,
                "Postgres binding request failed. Check the Dapr sidecar and database.");
    }

    @ExceptionHandler(JacksonException.class)
    public ProblemDetail invalidBindingResponse(JacksonException error) {
        LOG.error("Could not parse the binding response", error);
        return ProblemDetail.forStatusAndDetail(HttpStatus.INTERNAL_SERVER_ERROR,
                "The booking data could not be processed.");
    }
}
