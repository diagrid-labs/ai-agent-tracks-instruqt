package io.diagrid.university.pubsub.warehouse;

import io.dapr.client.DaprClientBuilder;
import io.dapr.client.DaprPreviewClient;
import io.dapr.utils.TypeRef;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;

import jakarta.annotation.PreDestroy;

import java.util.concurrent.CountDownLatch;

@Component
public class OrderStream implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(OrderStream.class);

    // Streaming subscriptions live on the preview client.
    private final DaprPreviewClient client = new DaprClientBuilder().buildPreviewClient();
    private final CountDownLatch shutdown = new CountDownLatch(1);
    private Disposable subscription;

    @Override
    public void run(ApplicationArguments args) {
        // The app opens the stream itself: pub/sub component `pubsub`, topic `orders`. Each
        // event is deserialized into an Order and the stream acknowledges it for us, so this
        // demo always reports success.
        subscription = client.subscribeToTopic("pubsub", "orders", TypeRef.get(Order.class))
                .subscribe(order -> log.info("warehouse received order {}", order.orderId()),
                        error -> log.error("warehouse stream ended", error));

        // The Flux alone does not keep the JVM alive: its threads are daemon threads and
        // there is no web server. The main thread waits here until SIGTERM closes the context.
        try {
            shutdown.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @PreDestroy
    void close() throws Exception {
        shutdown.countDown();
        if (subscription != null) {
            subscription.dispose();
        }
        client.close();
    }
}
