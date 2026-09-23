# 接口压测 SOP 模板

将本模板放入具体压测套件的 README，并按实际接口填写。目标是让第一次执行的人只需准备 Token、填写少数配置、执行一个命令。

## 0. 套件声明

README 必须写明：

- 被压接口清单：方法 + 路径 + 用途。
- 每个场景的粒度：单接口（写明接口名）或混压（写明接口与流量配比）。
- 负载模型：开放式（arrival-rate，适合容量测试）或封闭式（VU，适合冒烟/浸泡）。
- 场景清单：smoke / 单接口基线 / 单接口梯度容量 / 浸泡 / 混压，各自目的与档位。

单接口场景与混压场景分开定义、分开执行；混压场景必须先有对应单接口结果作参照。多接口混合的脚本必须按接口设置 tag 或 URL 分组，保证指标可按接口拆分。

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
./run.sh [scenario]
```

入口脚本负责：

1. 检查 `k6`、`jq`、`node` 和配置文件。
2. 检查 Token 存在、未过期且目标地址可解析。
3. 检查同一套件没有其他 k6 进程。
4. 自动创建 `results/YYYYMMDD/HHmmss_<environment>_<scenario>_<granularity>/`，granularity 为接口名或 `mixed`。
5. 启动唯一 k6 场景并保存 `run.log`、`summary.json`。

配置或前置检查失败时，入口脚本必须在启动 k6 前退出。三层报告由执行者按固定模板撰写和更新，入口脚本不负责。

## 3. 查看结果

优先查看 `最新压测报告.md` 和当轮 `结果摘要.md`，需要追溯时再看原始文件：

```text
最新压测报告.md  以接口为章节的最新有效压测
轮次索引.md      全部历史轮次，一行一轮
结果摘要.md      当轮明细
summary.json     k6 原始汇总
run.log          完整运行过程
```

报告必须写明本轮压测粒度，并区分：鉴权失败、网络 EOF/timeout、普通 HTTP 失败、设计内 503、响应字段错误和字段降级。混压轮必须给出按接口拆分的 P95/P99 与失败率，拆不出来要写明。没有采集到的 L1/L2/DB 实际命中率写明"本轮未采集"，不能用样本比例代替。

报告分三层维护：每轮目录内 `结果摘要.md`；`RESULTS_ROOT/轮次索引.md` 汇总历史轮次，只增不改；`RESULTS_ROOT/最新压测报告.md` 以接口为章节，每章为该接口最新有效轮摘要加历史轮次列表，混压/链路单独成章，每轮结束同步更新。报告只保留关键信息：异常全为 0 写"异常：无"，单轮摘要正文 ≤50 行、每接口章节 ≤30 行。
