# 业务场景：购物车优惠计算（函数式）

## 编码前设计

优惠规则是纯函数，输入不可变购物车快照，输出折扣金额。计算不访问数据库、不修改订单，便于单测和缓存；持久化在计算完成后执行。

## 完整示例

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.function.Function;
import java.util.logging.Logger;

/**
 * 演示函数式风格下的购物车优惠计算。
 *
 * <p>优惠规则只读取不可变快照，不访问外部资源，也不修改输入对象。
 */
public final class FunctionalDiscountExample {
    /**
     * 记录一次优惠计算的最终结果和总耗时。
     */
    private static final Logger LOGGER = Logger.getLogger(FunctionalDiscountExample.class.getName());
    /**
     * 禁止实例化示例入口类。
     */
    private FunctionalDiscountExample() {}
    /**
     * 组装示例购物车和优惠规则并输出应付金额。
     *
     * @param args 命令行参数，本示例不使用
     */
    public static void main(String[] args) {
        long startedAt = System.nanoTime();
        Cart cart = new Cart(List.of(new Item("sku-1", new BigDecimal("30.00"), 2)), true);
        List<Function<Cart, BigDecimal>> rules = List.of(
            value -> value.member() ? value.subtotal().multiply(new BigDecimal("0.10")) : BigDecimal.ZERO,
            value -> value.subtotal().compareTo(new BigDecimal("50.00")) >= 0
                ? new BigDecimal("5.00") : BigDecimal.ZERO
        );

        BigDecimal payable = calculatePayable(cart, rules);
        long elapsedMs = (System.nanoTime() - startedAt) / 1_000_000;
        LOGGER.info(() -> "[cart-service][discount][discount_calculated][success] payable="
            + payable + " elapsed_ms=" + elapsedMs);
        System.out.println(payable);
    }

    /**
     * 组合优惠规则并计算最终应付金额。
     *
     * @param cart 不可变购物车快照
     * @param rules 按顺序执行的纯优惠规则
     * @return 不小于零的应付金额
     */
    static BigDecimal calculatePayable(Cart cart, List<Function<Cart, BigDecimal>> rules) {
        // 优惠规则保持纯函数，计算阶段不修改购物车或访问外部资源。
        BigDecimal discount = rules.stream()
            .map(rule -> rule.apply(cart))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
        return cart.subtotal().subtract(discount).max(BigDecimal.ZERO);
    }

    /**
     * 表示计算优惠所需的不可变购物车快照。
     *
     * @param items 商品明细，不可为 {@code null}
     * @param member 是否为会员
     */
    record Cart(List<Item> items, boolean member) {
        /**
         * 复制明细，确保优惠计算使用稳定快照。
         */
        Cart { items = List.copyOf(items); }
        /**
         * 计算商品明细金额之和。
         *
         * @return 商品明细金额之和
         */
        BigDecimal subtotal() {
            return items.stream()
                .map(item -> item.unitPrice().multiply(BigDecimal.valueOf(item.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    /**
     * 表示购物车中的商品及购买数量。
     *
     * @param sku 商品唯一标识
     * @param unitPrice 商品单价
     * @param quantity 购买数量
     */
    record Item(String sku, BigDecimal unitPrice, int quantity) {}
}
```

## 设计与性能

规则数量较少时，具名函数和顺序执行比复杂高阶抽象更易读。商品数量很大时，应先生成一次购物车汇总，避免每条规则重复遍历明细；货币计算必须使用统一精度和舍入策略。
