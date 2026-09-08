# 业务场景：扣减库存（并发）

## 编码前设计

库存约束由数据库原子条件更新保证，应用层不使用进程内锁作为最终一致性手段。扣减结果必须区分成功、库存不足和系统错误。

## 完整示例

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * 演示并发扣减库存的原子操作。
 *
 * <p>示例仅覆盖单进程场景；多实例部署应改用数据库条件更新或分布式库存服务。
 */
public final class ConcurrentInventoryExample {
    /**
     * 禁止实例化示例入口类。
     */
    private ConcurrentInventoryExample() {}
    /**
     * 执行一次库存扣减示例。
     *
     * @param args 命令行参数，本示例不使用
     */
    public static void main(String[] args) {
        Inventory inventory = new InMemoryInventory();
        System.out.println(inventory.decrease("sku-1", 2));
    }

    /**
     * 库存扣减边界，返回明确的业务结果。
     */
    interface Inventory {
        /**
         * 尝试原子扣减指定数量。
         *
         * @param sku 商品唯一标识
         * @param quantity 扣减数量，必须为正数
         * @return 扣减状态和剩余库存
         */
        DecreaseResult decrease(String sku, int quantity);
    }

    /**
     * 使用 CAS（比较并交换）模拟单进程安全扣减。
     */
    static final class InMemoryInventory implements Inventory {
        /**
         * 记录库存不足和扣减成功等必要业务事件。
         */
        private static final Logger LOGGER = Logger.getLogger(InMemoryInventory.class.getName());
        /**
         * 商品库存，使用原子整数保证单进程内的并发扣减。
         */
        private final Map<String, AtomicInteger> stock = new ConcurrentHashMap<>();

        /**
         * 初始化示例库存。
         */
        InMemoryInventory() { stock.put("sku-1", new AtomicInteger(3)); }

        public DecreaseResult decrease(String sku, int quantity) {
            if (quantity <= 0) return DecreaseResult.invalid();
            AtomicInteger available = stock.get(sku);
            if (available == null) return DecreaseResult.notFound();
            // CAS 保证单进程并发扣减不出现负库存；多实例需改用数据库原子更新。
            while (true) {
                int current = available.get();
                if (current < quantity) {
                    LOGGER.log(Level.WARNING, "[inventory-service][stock][stock_decrease][sold_out] sku={0}", sku);
                    return DecreaseResult.soldOut();
                }
                if (available.compareAndSet(current, current - quantity)) {
                    LOGGER.log(Level.INFO, "[inventory-service][stock][stock_decreased][success] sku={0} remaining={1}",
                        new Object[] {sku, current - quantity});
                    return DecreaseResult.reserved(current - quantity);
                }
            }
        }
    }

    /**
     * 表示库存扣减结果和扣减后的剩余数量。
     *
     * @param status 扣减状态
     * @param remaining 扣减后的剩余数量
     */
    record DecreaseResult(Status status, int remaining) {
        /**
         * 创建扣减成功结果。
         *
         * @param remaining 扣减后的剩余数量
         * @return 成功结果
         */
        static DecreaseResult reserved(int remaining) { return new DecreaseResult(Status.RESERVED, remaining); }
        /**
         * 创建库存不足结果。
         *
         * @return 库存不足结果
         */
        static DecreaseResult soldOut() { return new DecreaseResult(Status.SOLD_OUT, 0); }
        /**
         * 创建商品不存在结果。
         *
         * @return 商品不存在结果
         */
        static DecreaseResult notFound() { return new DecreaseResult(Status.NOT_FOUND, 0); }
        /**
         * 创建参数无效结果。
         *
         * @return 参数无效结果
         */
        static DecreaseResult invalid() { return new DecreaseResult(Status.INVALID, 0); }
    }

    /**
     * 库存扣减结果状态。
     */
    enum Status { RESERVED, SOLD_OUT, NOT_FOUND, INVALID }
}
```

## 设计与性能

该示例演示单进程原子扣减；多实例生产系统应改为数据库条件更新或可靠的分布式库存服务，并为商品字段建立索引。高并发下需要观测 CAS 重试、热点商品、数据库锁等待和连接池容量。
