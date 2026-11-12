package io.diagrid.university.pubsub.invoicing;

public record Order(String orderId, String item, int quantity, String priority) {
}
