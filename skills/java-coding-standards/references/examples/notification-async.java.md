# 业务场景：支付成功通知（异步）

## 编码前设计

站内信、邮件和短信互不依赖，可以并发发送；每个通道有独立超时和错误结果。异步方法不能调用阻塞 SDK，重试必须携带幂等键。

## 完整示例

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * 演示异步并发发送支付成功通知。
 *
 * <p>各通知通道相互独立，单个通道失败不会阻止其他通道完成。
 */
public final class AsyncNotificationExample {
    /**
     * 禁止实例化示例入口类。
     */
    private AsyncNotificationExample() {}
    /**
     * 启动站内信、邮件和短信三个通知通道。
     *
     * @param args 命令行参数，本示例不使用
     */
    public static void main(String[] args) {
        NotificationService service = new NotificationService(List.of(
            new FakeSender("inbox"), new FakeSender("email"), new FakeSender("sms")));
        service.send(new Message("user-1", "order-1", "支付成功"))
            .thenAccept(System.out::println)
            .toCompletableFuture()
            .join();
    }

    /**
     * 编排多渠道通知，并收集每个通道的成功或失败结果。
     */
    static final class NotificationService {
        /**
         * 记录通道降级和整组通知完成等必要业务事件。
         */
        private static final Logger LOGGER = Logger.getLogger(NotificationService.class.getName());
        /**
         * 可用的通知渠道。
         */
        private final List<NotificationSender> senders;

        /**
         * 创建通知服务。
         *
         * @param senders 可用通知渠道，按调用顺序保存
         */
        NotificationService(List<NotificationSender> senders) { this.senders = List.copyOf(senders); }

        /**
         * 并发发送通知并等待所有通道给出结果。
         *
         * @param message 待发送消息
         * @return 每个通道的结果，不因单个通道失败而整体失败
         */
        CompletionStage<List<SendResult>> send(Message message) {
            long startedAt = System.nanoTime();
            // 通知通道相互独立，可以并发执行；每个通道单独记录失败结果。
            List<CompletableFuture<SendResult>> tasks = senders.stream()
                .map(sender -> sender.send(message)
                    .orTimeout(2, java.util.concurrent.TimeUnit.SECONDS)
                    .handle((ignored, error) -> error == null
                        ? SendResult.sent(sender.name())
                        : logFailure(sender.name(), error))
                )
                .toList();
            return CompletableFuture.allOf(tasks.toArray(CompletableFuture[]::new))
                .thenApply(ignored -> {
                    long elapsedMs = (System.nanoTime() - startedAt) / 1_000_000;
                    LOGGER.log(Level.INFO, "[notification-service][payment_notification][notification_completed][success] order_id={0} elapsed_ms={1}",
                        new Object[] {message.orderId(), elapsedMs});
                    return tasks.stream().map(CompletableFuture::join).toList();
                });
        }

        /**
         * 记录单个通道失败并转换为可聚合的业务结果。
         *
         * @param channel 失败的通知渠道
         * @param error 通道失败原因
         * @return 失败结果
         */
        private SendResult logFailure(String channel, Throwable error) {
            LOGGER.log(Level.WARNING, "[notification-service][payment_notification][notification_channel][degraded] channel={0} error_type={1}",
                new Object[] {channel, error.getClass().getSimpleName()});
            return SendResult.failed(channel, error.getClass().getSimpleName());
        }
    }

    /**
     * 单个通知渠道的异步发送边界。
     */
    interface NotificationSender {
        /**
         * 返回渠道业务名称。
         *
         * @return 渠道业务名称
         */
        String name();
        /**
         * 异步发送消息。
         *
         * @param message 待发送消息
         * @return 发送完成或失败时完成的异步结果
         */
        CompletableFuture<Void> send(Message message);
    }

    /**
     * 用于示例运行的异步通知渠道。
     *
     * @param name 渠道业务名称
     */
    record FakeSender(String name) implements NotificationSender {
        /**
         * 创建示例通知渠道。
         *
         * @param name 渠道业务名称
         */
        public FakeSender {}

        /**
         * @return 渠道名称
         */
        @Override
        public String name() { return name; }

        /**
         * @param message 待发送消息
         * @return 异步发送结果
         */
        @Override
        public CompletableFuture<Void> send(Message message) {
            return CompletableFuture.runAsync(() -> { });
        }
    }

    /**
     * 支付成功通知内容。
     *
     * @param userId 接收用户唯一标识
     * @param orderId 关联订单唯一标识
     * @param content 通知内容
     */
    record Message(String userId, String orderId, String content) {}
    /**
     * 单个通知渠道的发送结果。
     *
     * @param channel 通知渠道
     * @param success 是否发送成功
     * @param error 失败原因，成功时为 {@code null}
     */
    record SendResult(String channel, boolean success, String error) {
        /**
         * 创建成功结果。
         *
         * @param channel 通知渠道
         * @return 成功结果
         */
        static SendResult sent(String channel) { return new SendResult(channel, true, null); }
        /**
         * 创建失败结果。
         *
         * @param channel 通知渠道
         * @param error 失败原因
         * @return 失败结果
         */
        static SendResult failed(String channel, String error) { return new SendResult(channel, false, error); }
    }
}
```

## 设计与性能

通道数量可控时并发可降低总延迟；数量不可控时必须增加并发上限和专用执行器。生产实现还需要取消策略、重试退避、幂等键和结果持久化，避免重复通知。
