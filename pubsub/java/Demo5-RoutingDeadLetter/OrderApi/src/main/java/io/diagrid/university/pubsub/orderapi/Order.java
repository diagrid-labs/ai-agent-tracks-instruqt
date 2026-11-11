package io.diagrid.university.pubsub.orderapi;

// Record components are serialized in declaration order, which keeps the keys in the
// order of the Order contract.
public record Order(String orderId, String item, int quantity, String priority) {
}
