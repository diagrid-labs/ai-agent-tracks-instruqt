package io.diagrid.university.bindings.engineering;

import io.dapr.exceptions.DaprException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

// Turns exceptions into the error bodies of the HTTP contract, in one place, so the controller
// methods only describe the happy path.
@RestControllerAdvice
class ApiErrors {

    private static final Logger log = LoggerFactory.getLogger(ApiErrors.class);

    record ErrorBody(String error) {
    }

    // A failed Dapr call surfaces as a DaprException when the controller blocks on it.
    @ExceptionHandler(DaprException.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    ErrorBody bindingFailed(DaprException e) {
        log.warn("engineering binding call failed: {}", e.getMessage());
        return new ErrorBody("BINDING_FAILED");
    }
}
