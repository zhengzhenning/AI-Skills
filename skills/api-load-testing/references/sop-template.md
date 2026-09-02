# 接口压测 SOP 模板

将本模板放入具体压测套件的 README，并按实际接口填写。目标是让第一次执行的人只需准备 Token、填写少数配置、执行一个命令。

## 1. 准备配置

```bash
cp config.example.json config.local.json
```

只修改以下字段：

```json
{
  "BASE_URL": "https://stg-api.example.com",
  "AUTH_FILE": "./data/auth.local.json",
  "DATA_FILE": "./data/request-samples.json",
  "RESULTS_ROOT": "./results"
}
```

Token 只放在 `AUTH_FILE`，不写入命令行、脚本、日志或报告。

## 2. 执行

```bash
./run.sh
```

入口脚本负责：

1. 检查 `k6`、`jq`、`node` 和配置文件。
2. 检查 Token 存在、未过期且目标地址可解析。
3. 检查同一套件没有其他 k6 进程。
4. 自动创建 `results/YYYYMMDD/HHmmss_<environment>_<scenario>/`。
5. 启动唯一 k6 场景并保存 `run.log`、`summary.json` 和中文摘要。

配置或前置检查失败时，入口脚本必须在启动 k6 前退出。

## 3. 查看结果

优先查看中文摘要，再查看：

```text
summary.json  k6 原始汇总
run.log       完整运行过程
结果摘要.md   每档并发、P95、失败、503 和拐点结论
```

报告必须区分：鉴权失败、网络 EOF/timeout、普通 HTTP 失败、设计内 503、响应字段错误和字段降级。没有采集到的 L1/L2/DB 实际命中率写明“本轮未采集”，不能用样本比例代替。
