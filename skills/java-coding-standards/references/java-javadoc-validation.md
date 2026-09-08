# Java Javadoc 版本与校验

## 先识别项目能力

引入版本相关语法前，依次检查构建文件的源码/目标级别、CI 使用的 JDK、同模块既有文档风格，以及 `doclint`、自定义 doclet/taglet、Checkstyle 或注释检查插件。不得仅依据本机 JDK 版本决定语法。

## 版本选择

- 所有常见 Java 版本均支持传统 `/** ... */`、`@param`、`@return`、`@throws`、`@see`、`@since`、`@deprecated`。
- `@Deprecated(since, forRemoval)` 需要 Java 9 及以上。
- `{@summary ...}` 需要 JDK 10；`{@return ...}` 需要 JDK 16；`{@snippet ...}` 需要 JDK 18；`///` Markdown 文档注释需要 JDK 23。项目不支持时使用传统语法。
- `@apiNote`、`@implSpec`、`@implNote` 只有项目通过 `-tag`、taglet 或既有任务支持时才使用。

## 验证顺序

1. 优先运行项目已有的格式化、静态检查、Javadoc 或文档聚合任务。
2. 编译受影响模块，确认标签、链接、源码级别和注解元素有效。
3. 项目提供 Javadoc 任务时使用既有 `doclint` 设置，检查无效 HTML、缺失标签、错误链接和摘要截取。
4. 纯注释修改检查 diff，确保没有签名、逻辑、导入或大范围格式变化。

不要自行拼接通用 `javadoc` 命令绕过项目类路径、模块路径、生成源或 taglet 配置；不要通过关闭 `doclint` 或降低门禁掩盖错误。失败若来自未修改代码或环境，应报告原始错误和影响，不擅自扩大修改范围。
