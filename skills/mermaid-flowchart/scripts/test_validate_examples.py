"""Mermaid 流程图技能的回归测试。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_FILE = SKILL_DIR / "SKILL.md"
REFERENCE_FILE = SKILL_DIR / "references" / "mermaid-syntax.md"
OPENAI_FILE = SKILL_DIR / "agents" / "openai.yaml"
VALIDATOR = Path(__file__).with_name("validate_examples.py")


class SkillContentTest(unittest.TestCase):
    """检查核心流程图规范和显式触发策略。"""

    def test_requires_explicit_invocation(self) -> None:
        skill_content = SKILL_FILE.read_text(encoding="utf-8")
        openai_content = OPENAI_FILE.read_text(encoding="utf-8")

        self.assertIn("仅在用户明确指定 $mermaid-flowchart 时使用", skill_content)
        self.assertIn("allow_implicit_invocation: false", openai_content)
        self.assertIn("$mermaid-flowchart", openai_content)

    def test_defines_direction_and_node_semantics(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("业务流程默认使用 `flowchart TB`", content)
        self.assertIn("判断使用菱形节点", content)
        self.assertIn("开始和结束使用体育场形节点", content)

    def test_requires_labeled_decision_edges(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("判断节点的每条出边都必须标注条件", content)
        self.assertIn("条件互斥且覆盖预期结果", content)

    def test_reference_contains_copyable_subgraph_syntax(self) -> None:
        self.assertTrue(REFERENCE_FILE.is_file(), "缺少流程图语法参考文件")
        content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("subgraph Backend[后端系统]", content)
        self.assertIn("direction TB", content)

    def test_defines_exception_and_fallback_color_semantics(self) -> None:
        skill_content = SKILL_FILE.read_text(encoding="utf-8")
        reference_content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("异常、失败或终止节点必须使用 `exception` 红色语义类", skill_content)
        self.assertIn("兜底、降级或重试节点必须使用 `fallback` 黄色语义类", skill_content)
        self.assertIn("classDef exception", reference_content)
        self.assertIn("classDef fallback", reference_content)

    def test_requires_visual_distinction_for_nested_regions(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("嵌套 `subgraph`", content)
        self.assertIn("每一层必须使用独立的语义类", content)
        self.assertIn("超过三层时必须拆图", content)

    def test_retry_example_uses_fallback_then_exception_semantics(self) -> None:
        content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("Backoff[等待退避时间]:::fallback", content)
        self.assertIn("Alert[告警并结束]:::exception", content)

    def test_defines_crossing_policy_and_exception_boundary(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("默认禁止可避免的连线交叉", content)
        self.assertIn("仍无法消除的交叉可以保留", content)
        self.assertIn("反转真实流程方向", content)
        self.assertIn("重复声明同一业务节点", content)
        self.assertIn("必须在图外说明", content)
        self.assertIn("多处不可避免交叉", content)

    def test_reference_contains_wrong_and_correct_crossing_examples(self) -> None:
        content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("### 错误示例：可避免的交叉", content)
        self.assertIn("### 改正示例：调整分支位置", content)
        self.assertIn("### 错误示例：通过复制节点掩盖交叉", content)


class ValidatorTest(unittest.TestCase):
    """检查验证器的静态校验和渲染降级行为。"""

    def run_validator(self, content: str, *options: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "example.md"
            source.write_text(content, encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = ""
            return subprocess.run(
                [sys.executable, str(VALIDATOR), *options, str(source)],
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )

    def test_valid_flowchart_passes_static_validation_without_mmdc(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    Start([开始]) --> Check{是否有效}
    Check -->|是| Done([结束])
    Check -->|否| Reject[拒绝请求]
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("未渲染验证", result.stdout)

    def test_unclosed_subgraph_fails(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart LR
    subgraph Backend[后端系统]
        API[API] --> DB[(数据库)]
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("subgraph", result.stderr)
        self.assertIn("未闭合", result.stderr)

    def test_exception_class_requires_red_palette(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    Start([开始]) --> Failed[处理失败]:::exception
    classDef exception fill:#fef3c7,stroke:#b45309,color:#78350f
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("exception 必须使用规定的红色系", result.stderr)

    def test_fallback_class_requires_yellow_palette(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    Start([开始]) --> Cache[读取缓存]:::fallback
    classDef fallback fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("fallback 必须使用规定的黄色系", result.stderr)

    def test_semantic_classes_with_matching_palettes_pass(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    Start([开始]) --> Failed[处理失败]:::exception
    Failed --> Cache[读取缓存兜底]:::fallback
    classDef exception fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    classDef fallback fill:#fef3c7,stroke:#b45309,color:#78350f
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_nested_subgraphs_without_distinct_classes_fail(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    subgraph Outer[L1：外层]
        subgraph Inner[L2：内层]
            A --> B
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("每个区域必须使用独立的语义类", result.stderr)

    def test_nested_subgraphs_with_distinct_classes_pass(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    subgraph Outer[L1：外层]
        subgraph Inner[L2：内层]
            A --> B
        end
    end
    classDef regionL1 fill:#eff6ff,stroke:#2563eb,color:#1e3a8a
    classDef regionL2 fill:#ecfdf5,stroke:#059669,color:#064e3b
    class Outer regionL1
    class Inner regionL2
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_more_than_three_nested_subgraphs_fail(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    subgraph L1[L1：一级]
        subgraph L2[L2：二级]
            subgraph L3[L3：三级]
                subgraph L4[L4：四级]
                    A --> B
                end
            end
        end
    end
    classDef c1 fill:#eff6ff,stroke:#2563eb
    classDef c2 fill:#ecfdf5,stroke:#059669
    classDef c3 fill:#fef3c7,stroke:#b45309
    classDef c4 fill:#fee2e2,stroke:#b91c1c
    class L1 c1
    class L2 c2
    class L3 c3
    class L4 c4
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("嵌套超过三层", result.stderr)

    def test_ignores_other_mermaid_diagram_types_in_markdown(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    A->>B: 请求
```

```mermaid
flowchart LR
    A[输入] --> B[输出]
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("1 个图", result.stdout)

    def test_require_render_fails_without_mmdc(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart TB
    A[开始] --> B[结束]
```
""",
            "--require-render",
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("mmdc", result.stderr)

    def test_bundled_examples_pass_static_validation(self) -> None:
        env = os.environ.copy()
        env["PATH"] = ""
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(SKILL_FILE), str(REFERENCE_FILE)],
            capture_output=True,
            check=False,
            env=env,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_renderer_must_create_svg_before_reporting_success(self) -> None:
        true_command = shutil.which("true")
        self.assertIsNotNone(true_command)
        with tempfile.TemporaryDirectory() as temp_dir:
            bin_dir = Path(temp_dir) / "bin"
            bin_dir.mkdir()
            (bin_dir / "mmdc").symlink_to(true_command)
            source = Path(temp_dir) / "example.mmd"
            source.write_text("flowchart LR\n    A --> B\n", encoding="utf-8")
            env = os.environ.copy()
            env["PATH"] = str(bin_dir)
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(source)],
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("没有生成 SVG", result.stderr)


if __name__ == "__main__":
    unittest.main()
