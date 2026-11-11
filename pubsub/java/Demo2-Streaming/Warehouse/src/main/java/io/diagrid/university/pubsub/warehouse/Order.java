package io.diagrid.university.pubsub.warehouse;

public record Order(String orderId, String item, int quantity, String priority) {
}
