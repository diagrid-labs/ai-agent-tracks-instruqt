package io.diagrid.university.pubsub.warehouse;

import io.dapr.client.DaprPreviewClient;
import io.dapr.utils.TypeRef;
import io.grpc.Status;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@Component
public class OrderStream implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(OrderStream.class);

    private final DaprPreviewClient client;
    private final JsonMapper mapper;
    // Set on the startup thread, disposed on the shutdown thread: volatile makes the write visible.
    private volatile Disposable subscription;

    OrderStream(DaprPreviewClient client, JsonMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    @Override
    public void run(ApplicationArguments args) {
        // The app opens the stream itself: pub/sub component `pubsub`, topic `orders`. No
        // Subscription file and no /dapr/subscribe endpoint are involved.
        // The SDK answers Dapr SUCCESS for every message it hands to this Flux, so this demo
        // always acknowledges. The data is taken as raw bytes rather than TypeRef<Order>: a
        // message the SDK cannot deserialize into the requested type is answered DROP and ends
        // the whole Flux with an error, which would close the stream.
        subscription = client.subscribeToTopic("pubsub", "orders", TypeRef.BYTE_ARRAY)
                .subscribe(this::receiveOrder,
                        this::streamFailed,
                        () -> log.info("warehouse stream closed by the sidecar"));
        // run() returns straight away. spring.main.keep-alive keeps the JVM running (the
        // stream's threads are daemon threads and there is no web server) until SIGTERM.
    }

    // Never throws: if this callback threw, Reactor would cancel the Flux, which closes the
    // stream to the sidecar, and the SDK does not reopen it.
    private void receiveOrder(byte[] data) {
        String orderId = readOrderId(data);
        if (orderId == null) {
            log.warn("warehouse dropped unreadable event");
        } else {
            log.info("warehouse received order {}", orderId);
        }
    }

    // The message holds the CloudEvent data as raw bytes of JSON. Returns its orderId, or
    // null if the data is not a JSON object with a string orderId.
    private String readOrderId(byte[] data) {
        try {
            JsonNode orderId = mapper.readTree(data).path("orderId");
            return orderId.isString() ? orderId.asString() : null;
        } catch (JacksonException e) {
            return null;
        }
    }

    // A sidecar that shuts down (dapr stop, Ctrl+C) ends the stream with UNKNOWN "stream closed",
    // usually before this app gets its own SIGTERM. That is a normal stop, not an error. Any
    // other error, such as the connection to the sidecar dropping, ends the stream for good.
    private void streamFailed(Throwable error) {
        Status status = Status.fromThrowable(error);
        if (status.getCode() == Status.Code.UNKNOWN && "stream closed".equals(status.getDescription())) {
            log.info("warehouse stream closed by the sidecar");
        } else {
            log.error("warehouse stream ended", error);
        }
    }

    @PreDestroy
    void close() {
        // Disposing the subscription closes the stream. The client itself is a bean, which
        // Spring closes after this.
        if (subscription != null) {
            subscription.dispose();
        }
    }
}
