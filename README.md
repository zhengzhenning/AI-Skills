# AI Skills

集中维护个人 AI 技能，并通过软链接供不同 AI 工具使用。`skills/` 是唯一内容源，工具目录中不保存副本。

## 目录

```text
AI-Skills/
├── skills/                   # 中央技能
│   └── api-load-testing/
└── scripts/                  # 安装、卸载和状态检查
```

每个技能遵循 Agent Skills 基础结构：

```text
skill-name/
├── SKILL.md                  # 必需：触发说明和核心流程
├── agents/                   # 可选：工具专用元数据
├── references/               # 可选：按需读取的详细资料
├── scripts/                  # 可选：可重复执行的脚本
└── assets/                   # 可选：输出所需模板或资源
```

技能目录内不放 README、变更记录等辅助文档，避免增加上下文和维护成本。

## 安装

```bash
./scripts/install.sh codex api-load-testing
./scripts/install.sh claude api-load-testing
./scripts/install.sh cursor api-load-testing
```

默认安装位置：

| 工具 | 目录 |
| --- | --- |
| Codex | `${CODEX_HOME:-~/.codex}/skills/` |
| Claude | `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/` |
| Cursor | `${CURSOR_CONFIG_DIR:-~/.cursor}/skills/` |

其他工具或非标准目录可临时指定：

```bash
AI_SKILLS_TARGET_DIR=/path/to/skills ./scripts/install.sh custom api-load-testing
```

安装程序只创建软链接；如果目标位置已经存在同名文件或指向其他位置的链接，会停止并提示，不会覆盖。

## 检查与卸载

```bash
./scripts/status.sh codex api-load-testing
./scripts/uninstall.sh codex api-load-testing
```

卸载只移除由本项目安装且仍指向中央技能的软链接，不删除中央技能内容。

## 维护

直接修改 `skills/<技能名>/`，所有软链接安装会立即生效。提交前运行：

```bash
./scripts/validate.sh api-load-testing
```

如果本机具备 Codex 官方校验器及其 Python YAML 依赖，脚本会优先执行官方校验；否则自动完成不依赖第三方包的基础检查。

个人 Token、本地配置、压测结果和其他敏感信息不得进入本仓库。

不同 AI 工具对技能元数据和显式触发的支持程度不同。`SKILL.md` 保存通用规则，`agents/` 保存工具专用约束；无法强制显式触发的工具，应通过工具自身规则或适配配置补充限制。
