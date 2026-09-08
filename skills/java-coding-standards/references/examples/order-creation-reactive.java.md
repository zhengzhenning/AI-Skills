# 业务场景：创建订单（Vert.x 响应式）

## 编码前设计

异步主链按“校验 → 读取上下文 → 计算 → 保存 → 转换”排列。Repository 只返回 `Future`，不得阻塞事件循环；计算阶段保持无副作用。

## 完整示例

```java
import io.vertx.core.Future;
import io.vertx.core.Vertx;
import java.math.BigDecimal;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * 演示 Vert.x 响应式风格下的订单创建流程。
 *
 * <p>所有阶段通过 {@code Future} 串联，示例不在事件循环中执行阻塞 I/O。
 */
public final class ReactiveOrderExample {
    /**
     * 启动一次异步订单创建并在流程结束后关闭 Vert.x。
     *
     * @param args 命令行参数，本示例不使用
     */
    public static void main(String[] args) {
        Vertx vertx = Vertx.vertx();
        OrderService service = new OrderService(new OrderRepository(), new OrderCalculator());
        service.create(new CreateOrder("customer-1", "sku-1", 2))
            .onSuccess(System.out::println)
            .onFailure(Throwable::printStackTrace)
            .eventually(ignored -> vertx.close());
    }

    /**
     * 按业务顺序编排校验、数据读取、计算和保存。
     */
    static final class OrderService {
        /**
         * 记录订单创建最终结果和全链路耗时。
         */
        private static final Logger LOGGER = Logger.getLogger(OrderService.class.getName());
        private final OrderRepository repository;
        private final OrderCalculator calculator;

        OrderService(OrderRepository repository, OrderCalculator calculator) {
            this.repository = repository;
            this.calculator = calculator;
        }

        /**
         * 异步创建订单。
         *
         * @param request 创建订单请求
         * @return 成功时完成订单响应，失败时携带校验或 I/O 错误
         */
        Future<OrderResponse> create(CreateOrder request) {
            long startedAt = System.nanoTime();
            // 保持异步阶段按业务顺序排列，禁止在链中加入阻塞 I/O。
            return validate(request)
                .compose(ignored -> repository.loadContext(request.customerId(), request.sku()))
                .map(context -> calculator.calculate(request, context))
                .compose(repository::save)
                .map(order -> {
                    long elapsedMs = (System.nanoTime() - startedAt) / 1_000_000;
                    LOGGER.log(Level.INFO, "[order-service][order][order_created][success] order_id={0} total_elapsed_ms={1}",
                        new Object[] {order.id(), elapsedMs});
                    return new OrderResponse(order.id(), order.total());
                });
        }

        private Future<Void> validate(CreateOrder request) {
            if (request.quantity() <= 0) {
                return Future.failedFuture("quantity_must_be_positive");
            }
            return Future.succeededFuture();
        }
    }

    /**
     * 提供非阻塞订单上下文读取和保存能力。
     */
    static final class OrderRepository {
        Future<OrderContext> loadContext(String customerId, String sku) {
            return Future.succeededFuture(new OrderContext(new BigDecimal("19.90")));
        }

        Future<Order> save(OrderDraft draft) {
            return Future.succeededFuture(new Order("order-1", draft.total()));
        }
    }

    /**
     * 执行不产生副作用的订单金额计算。
     */
    static final class OrderCalculator {
        OrderDraft calculate(CreateOrder request, OrderContext context) {
            return new OrderDraft(context.unitPrice().multiply(BigDecimal.valueOf(request.quantity())));
        }
    }

    /**
     * 创建订单请求；数量必须为正数。
     *
     * @param customerId 客户唯一标识
     * @param sku 商品唯一标识
     * @param quantity 购买数量，必须为正数
     */
    record CreateOrder(String customerId, String sku, int quantity) {}
    /**
     * 订单计算所需的只读上下文。
     *
     * @param unitPrice 商品单价
     */
    record OrderContext(BigDecimal unitPrice) {}
    /**
     * 尚未持久化的订单草稿。
     *
     * @param total 订单总金额
     */
    record OrderDraft(BigDecimal total) {}
    /**
     * 已保存的订单。
     *
     * @param id 订单唯一标识
     * @param total 订单总金额
     */
    record Order(String id, BigDecimal total) {}
    /**
     * 创建订单接口的响应。
     *
     * @param orderId 订单唯一标识
     * @param total 订单总金额
     */
    record OrderResponse(String orderId, BigDecimal total) {}
}
```

## 设计与性能

不要在 `Future` 链中调用阻塞 JDBC 或同步 HTTP；真实实现应使用异步客户端。商品上下文应批量读取，避免按订单明细逐条查询；链条变长时按业务阶段提取方法，而不是把每个操作符包装成一行转发方法。
