# 业务场景：订单支付（命令式面向对象）

## 编码前设计

支付流程按“加载订单 → 校验状态 → 创建支付 → 更新订单”组织。金额计算和支付网关分别承担单一职责；订单状态更新必须幂等。

## 完整示例

```java
import java.math.BigDecimal;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 演示命令式面向对象风格下的订单支付流程。
 *
 * <p>示例通过幂等键避免重复创建支付单，并在支付成功后更新订单状态。
 */
public final class OrderPaymentExample {
    /**
     * 禁止实例化示例入口类。
     */
    private OrderPaymentExample() {}
    /**
     * 启动内存实现，演示一次可重复执行的支付请求。
     *
     * @param args 命令行参数，本示例不使用
     */
    public static void main(String[] args) {
        OrderRepository orders = new InMemoryOrderRepository();
        PaymentGateway payments = new FakePaymentGateway();
        PaymentService service = new PaymentService(orders, payments);

        PaymentResult result = service.pay("order-1001", "request-001");
        System.out.println(result);
    }

    /**
     * 编排订单支付业务，不直接依赖具体支付平台实现。
     */
    static final class PaymentService {
        /**
         * 记录支付完成和幂等命中等必要业务事件。
         */
        private static final Logger LOGGER = Logger.getLogger(PaymentService.class.getName());
        /**
         * 订单持久化边界。
         */
        private final OrderRepository orderRepository;
        /**
         * 第三方支付边界。
         */
        private final PaymentGateway paymentGateway;

        /**
         * 创建支付服务。
         *
         * @param orderRepository 订单持久化实现
         * @param paymentGateway 支付网关实现
         */
        PaymentService(OrderRepository orderRepository, PaymentGateway paymentGateway) {
            this.orderRepository = orderRepository;
            this.paymentGateway = paymentGateway;
        }

        /**
         * 为处于可支付状态的订单创建支付单。
         *
         * @param orderId 订单唯一标识
         * @param idempotencyKey 幂等键，用于避免重复创建支付单
         * @return 支付结果；已支付订单直接返回已有支付信息
         * @throws IllegalArgumentException 当订单不存在时抛出
         * @throws IllegalStateException 当订单不处于可支付状态时抛出
         */
        PaymentResult pay(String orderId, String idempotencyKey) {
            long startedAt = System.nanoTime();
            Order order = orderRepository.find(orderId);
            if (order == null) {
                throw new IllegalArgumentException("order_not_found: " + orderId);
            }
            // 幂等请求直接返回已完成支付，避免重复调用第三方支付接口。
            if (order.status() == OrderStatus.PAID) {
                LOGGER.log(Level.WARNING, "[order-service][payment][payment_idempotent_hit][success] order_id={0}", orderId);
                return new PaymentResult(order.id(), order.paymentId(), order.amount());
            }
            if (order.status() != OrderStatus.CREATED) {
                throw new IllegalStateException("order_not_payable: " + order.status());
            }

            // 支付网关调用必须携带幂等键，订单状态变更保持在支付成功之后。
            Payment payment = paymentGateway.create(idempotencyKey, order.id(), order.amount());
            Order paidOrder = order.markPaid(payment.id());
            orderRepository.save(paidOrder);
            long elapsedMs = (System.nanoTime() - startedAt) / 1_000_000;
            LOGGER.log(Level.INFO, "[order-service][payment][payment_completed][success] order_id={0} payment_id={1} elapsed_ms={2}",
                new Object[] {paidOrder.id(), payment.id(), elapsedMs});
            return new PaymentResult(paidOrder.id(), payment.id(), paidOrder.amount());
        }
    }

    /**
     * 订单持久化边界，真实实现应在保存时提供事务和幂等约束。
     */
    interface OrderRepository {
        /**
         * 查询订单。
         *
         * @param orderId 订单唯一标识
         * @return 订单，不存在时返回 {@code null}
         */
        Order find(String orderId);
        /**
         * 保存订单。
         *
         * @param order 待保存的订单
         */
        void save(Order order);
    }

    /**
     * 内存订单存储，仅用于演示业务编排。
     */
    static final class InMemoryOrderRepository implements OrderRepository {
        /**
         * 示例订单存储。
         */
        private final Map<String, Order> data = new ConcurrentHashMap<>();

        /**
         * 初始化一个待支付订单。
         */
        InMemoryOrderRepository() {
            data.put("order-1001", new Order("order-1001", new BigDecimal("99.90"), OrderStatus.CREATED, null));
        }

        public Order find(String orderId) { return data.get(orderId); }
        public void save(Order order) { data.put(order.id(), order); }
    }

    /**
     * 第三方支付平台边界，调用方必须传入幂等键。
     */
    interface PaymentGateway {
        /**
         * 创建支付单。
         *
         * @param idempotencyKey 幂等键
         * @param orderId 订单唯一标识
         * @param amount 支付金额
         * @return 已创建的支付单
         */
        Payment create(String idempotencyKey, String orderId, BigDecimal amount);
    }

    /**
     * 用于示例运行的支付网关。
     */
    static final class FakePaymentGateway implements PaymentGateway {
        /**
         * 创建模拟支付单。
         *
         * @param idempotencyKey 幂等键
         * @param orderId 订单标识
         * @param amount 支付金额
         * @return 支付单
         */
        public Payment create(String idempotencyKey, String orderId, BigDecimal amount) {
            Objects.requireNonNull(idempotencyKey, "idempotencyKey");
            return new Payment("payment-" + orderId, amount);
        }
    }

    /**
     * 订单支付状态。
     */
    enum OrderStatus { CREATED, PAID }
    /**
     * 表示第三方支付单及其金额。
     *
     * @param id 支付单唯一标识
     * @param amount 支付金额
     */
    record Payment(String id, BigDecimal amount) {}
    /**
     * 表示订单支付完成后的对外结果。
     *
     * @param orderId 订单唯一标识
     * @param paymentId 支付单唯一标识
     * @param amount 支付金额
     */
    record PaymentResult(String orderId, String paymentId, BigDecimal amount) {}
    /**
     * 表示订单及其支付状态。
     *
     * @param id 订单唯一标识
     * @param amount 订单金额
     * @param status 订单支付状态
     * @param paymentId 支付单唯一标识，未支付时为 {@code null}
     */
    record Order(String id, BigDecimal amount, OrderStatus status, String paymentId) {
        /**
         * 将订单标记为已支付。
         *
         * @param paymentId 支付单唯一标识
         * @return 已标记为已支付的新订单
         */
        Order markPaid(String paymentId) { return new Order(id, amount, OrderStatus.PAID, paymentId); }
    }
}
```

## 设计与性能

主流程没有混入 SQL 或第三方响应转换；重复支付直接返回已有结果。真实实现需要在持久化层增加唯一幂等约束和事务，金额使用 `BigDecimal`，订单查询必须使用索引。
