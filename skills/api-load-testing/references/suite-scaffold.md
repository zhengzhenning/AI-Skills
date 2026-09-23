# 新建压测套件脚手架

新建套件按本文件落地，满足仓库约束的最低要求：唯一入口、四项配置、内置场景、按接口打 tag、结构测试。

## 目录结构

```text
perf/k6/<suite>/
├── run.sh                  # 唯一入口
├── config.example.json     # 配置模板（提交）
├── config.local.json       # 本地配置（不提交）
├── data/
│   ├── auth.local.json     # Token（不提交）
│   └── request-samples.json
├── lib/scenario.js         # k6 场景与请求逻辑
├── test/structure.test.js  # 结构测试
└── results/                # 原始产物与三层报告
```

## config.example.json

```json
{
  "BASE_URL": "https://stg-api.example.com",
  "AUTH_FILE": "./data/auth.local.json",
  "DATA_FILE": "./data/request-samples.json",
  "RESULTS_ROOT": "./results"
}
```

## DATA_FILE 格式（request-samples.json）

```json
{
  "samples": [
    {
      "name": "create-order",
      "url": "/api/order/create",
      "method": "POST",
      "body": { "skuId": "SKU-001", "count": 1 },
      "cacheTier": "L1"
    }
  ],
  "mix": [
    { "name": "create-order", "weight": 1 },
    { "name": "order-query", "weight": 4 }
  ]
}
```

- `name`：接口标识，用作 k6 group 名，混压按它拆分指标；必须唯一。
- `cacheTier`：L1/L2/DB，可选，仅用于计划比例标注。
- `mix`：仅混压场景使用，按 weight 分发流量；单接口场景忽略。

## k6 场景骨架（lib/scenario.js）

场景命名固定：`smoke`、`baseline`、`ramp`（梯度容量）、`soak`、`mixed`。容量场景用开放式阶梯吞吐（ramping-arrival-rate，吞吐不随系统变慢下降），浸泡用封闭式定并发（constant-vus）；所有请求包在 `group(sample.name)` 内，实现按接口拆分。

```javascript
import http from 'k6/http';
import { check, group } from 'k6';
import { SharedArray } from 'k6/data';

const cfg = JSON.parse(open(__ENV.CONFIG_PATH));
const file = JSON.parse(open(cfg.DATA_FILE));
const samples = new SharedArray('samples', () => file.samples);
const auth = JSON.parse(open(cfg.AUTH_FILE));

export const options = {
  scenarios: {
    baseline: {                              // 基线：低吞吐跑通
      executor: 'constant-arrival-rate', rate: 5, timeUnit: '1s',
      duration: '3m', preAllocatedVUs: 5, maxVUs: 10, exec: 'hit',
    },
    ramp: {                                  // 梯度容量：开放式，找拐点
      executor: 'ramping-arrival-rate', startRate: 100, timeUnit: '1s',
      preAllocatedVUs: 50, maxVUs: 400, exec: 'hit',
      stages: [
        { duration: '2m', target: 100 },
        { duration: '5m', target: 400 },
        { duration: '5m', target: 800 },
      ],
    },
    soak: {                                  // 浸泡：中等负载长时间
      executor: 'constant-vus', vus: 50, duration: '45m', exec: 'hit',
    },
    // smoke / mixed 按同样结构定义；mixed 按 mix 权重选取样本
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<800'],
  },
};

export function hit() {
  const s = samples[0];                      // 单接口；mixed 场景按 mix 权重选取
  group(s.name, () => {
    const res = http.request(
      s.method, `${cfg.BASE_URL}${s.url}`,
      s.body ? JSON.stringify(s.body) : null,
      { headers: { 'Content-Type': 'application/json', Authorization: auth.token } }
    );
    check(res, { 'status 2xx': (r) => r.status >= 200 && r.status < 300 });
  });
}
```

## run.sh 骨架

```bash
#!/usr/bin/env bash
set -euo pipefail
SCENARIO="${1:-ramp}"            # smoke | baseline | ramp | soak | mixed
CONFIG="${2:-config.local.json}"

command -v k6 >/dev/null && command -v jq >/dev/null && command -v node >/dev/null \
  || { echo "缺少 k6/jq/node"; exit 1; }
[ -f "$CONFIG" ] || { echo "配置不存在: $CONFIG"; exit 1; }
BASE_URL=$(jq -r .BASE_URL "$CONFIG")
AUTH_FILE=$(jq -r .AUTH_FILE "$CONFIG")
RESULTS_ROOT=$(jq -r .RESULTS_ROOT "$CONFIG")
[ -s "$AUTH_FILE" ] || { echo "Token 文件为空"; exit 1; }
# Token 有效期检查按 AUTH_FILE 实际字段补充（如 expiresAt）
host="$(printf '%s' "$BASE_URL" | sed -E 's#https?://##; s#[:/].*##')"
nslookup "$host" >/dev/null || { echo "目标地址不可解析"; exit 1; }
pgrep -f "k6 run.*$(basename "$PWD")" >/dev/null && { echo "已有同套件 k6 进程"; exit 1; }

GRANULARITY="$SCENARIO"; [ "$SCENARIO" = mixed ] && GRANULARITY=mixed   # 单接口场景改取接口名
DIR="$RESULTS_ROOT/$(date +%Y%m%d)/$(date +%H%M%S)_${host%%.*}_${SCENARIO}_${GRANULARITY}"
mkdir -p "$DIR"
CONFIG_PATH="$PWD/$CONFIG" k6 run --scenario "$SCENARIO" --quiet \
  --summary-export "$DIR/summary.json" 2>&1 | tee "$DIR/run.log"
# 三层报告（结果摘要/轮次索引/最新压测报告）由执行者撰写，run.sh 不负责
```

## 结构测试示例（test/structure.test.js）

`package.json` 的 `npm test` 指向 `node --test test/`：

```javascript
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');

test('配置只开放四项字段', () => {
  const cfg = JSON.parse(fs.readFileSync('config.example.json'));
  assert.deepEqual(Object.keys(cfg).sort(),
    ['AUTH_FILE', 'BASE_URL', 'DATA_FILE', 'RESULTS_ROOT']);
});

test('样本字段完整且 name 唯一', () => {
  const data = JSON.parse(fs.readFileSync('data/request-samples.json'));
  const names = data.samples.map((s) => s.name);
  data.samples.forEach((s) => assert.ok(s.name && s.url && s.method, `${s.name} 缺字段`));
  assert.equal(new Set(names).size, names.length);
});

test('场景满足负载模型约束', () => {
  const src = fs.readFileSync('lib/scenario.js', 'utf8');
  assert.match(src, /ramping-arrival-rate/);   // 容量场景为开放式
  assert.match(src, /constant-vus/);           // 浸泡场景存在
  assert.match(src, /group\(s\.name\)/);       // 请求按接口分组
});
```
