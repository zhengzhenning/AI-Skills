"""Mermaid 时序图技能的回归测试。"""

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
    """检查核心绘制规范不会退回已知错误。"""

    def test_requires_explicit_invocation(self) -> None:
        skill_content = SKILL_FILE.read_text(encoding="utf-8")
        openai_content = OPENAI_FILE.read_text(encoding="utf-8")

        self.assertIn("仅在用户明确指定 $mermaid-sequence-diagram 时使用", skill_content)
        self.assertIn("allow_implicit_invocation: false", openai_content)
        self.assertIn("$mermaid-sequence-diagram", openai_content)

    def test_distinguishes_actor_participant_and_box(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("人、用户或外部业务角色使用 `actor`", content)
        self.assertIn("系统边界使用 `box`", content)

    def test_async_arrow_guidance_is_compatible(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("异步投递推荐使用 `-)` 或 `--)`", content)
        self.assertIn("目标渲染器不支持开放箭头", content)
        self.assertNotIn("异步投递只能使用", content)

    def test_box_syntax_uses_copyable_examples(self) -> None:
        content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("`box Aqua 核心域`", content)
        self.assertIn("`box 核心域`", content)
        self.assertNotIn("`box [颜色] 标题`", content)

    def test_requires_visual_distinction_for_nested_regions(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("只要逻辑区域块发生嵌套", content)
        self.assertIn("每一层必须使用独立的 `rect`", content)
        self.assertIn("`L1`、`L2`、`L3`", content)
        self.assertIn("超过三层时必须拆图", content)
        self.assertIn("同一语义使用同一色系", content)
        self.assertIn("不得复用完全相同的色值", content)

    def test_reference_covers_non_alt_nested_regions(self) -> None:
        content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("alt L1：请求合法", content)
        self.assertIn("loop L2：最多重试 3 次", content)
        self.assertIn("critical L3：提交事务", content)

    def test_defines_exception_and_fallback_color_semantics(self) -> None:
        skill_content = SKILL_FILE.read_text(encoding="utf-8")
        reference_content = REFERENCE_FILE.read_text(encoding="utf-8")

        self.assertIn("`%% semantic:exception`", skill_content)
        self.assertIn("异常、失败或终止分支必须使用红色系", skill_content)
        self.assertIn("`%% semantic:fallback`", skill_content)
        self.assertIn("兜底、降级或重试分支必须使用黄色系", skill_content)
        self.assertIn("semantic:exception", reference_content)
        self.assertIn("semantic:fallback", reference_content)
        self.assertRegex(
            reference_content,
            r"semantic:fallback\s+rect rgba\(254, 243, 199, 0\.35\)\s+loop L2：最多重试 3 次",
        )

    def test_requires_automatic_message_numbering(self) -> None:
        content = SKILL_FILE.read_text(encoding="utf-8")

        self.assertIn("所有完整时序图必须启用 `autonumber`", content)
        self.assertIn("第二条有效语句必须是 `autonumber`", content)
        self.assertIn("禁止在消息文本中手写序号", content)


class ValidatorTest(unittest.TestCase):
    """检查示例验证器的静态校验和渲染降级行为。"""

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

    def test_missing_autonumber_fails(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    participant A
    participant B
    A->>B: 请求
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("第二条有效语句必须是 autonumber", result.stderr)

    def test_autonumber_after_participant_fails(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    participant A
    autonumber
    A->>B: 请求
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("第二条有效语句必须是 autonumber", result.stderr)

    def test_valid_document_passes_static_validation_without_mmdc(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    participant A
    participant B
    A->>B: 请求
    B-->>A: 响应
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("未渲染验证", result.stdout)

    def test_unclosed_control_block_fails(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    alt 成功
        A->>B: 请求
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("未闭合", result.stderr)

    def test_nested_regions_without_rect_distinction_fail(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    alt L1：请求合法
        loop L2：最多重试 3 次
            A->>B: 调用
        end
    else L1：请求非法
        A-->>B: 拒绝
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("独立 rect", result.stderr)

    def test_nested_regions_with_distinct_rect_colors_pass(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    rect rgba(219, 234, 254, 0.35)
        alt L1：请求合法
            rect rgba(220, 252, 231, 0.35)
                loop L2：最多重试 3 次
                    A->>B: 调用
                end
            end
        else L1：请求非法
            A-->>B: 拒绝
        end
    end
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_nested_regions_with_reused_color_fail(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    rect rgba(219, 234, 254, 0.35)
        alt L1：请求合法
            rect rgba(219, 234, 254, 0.35)
                opt L2：需要补充校验
                    A->>B: 校验
                end
            end
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("颜色不得重复", result.stderr)

    def test_multiple_sibling_regions_without_rects_fail(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    alt 请求有效
        A->>B: 处理请求
    else 请求无效
        A-->>B: 拒绝请求
    end
    loop 最多重试 3 次
        A->>B: 重试调用
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("多个逻辑区域块", result.stderr)

    def test_nested_region_without_level_title_fails(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    rect rgba(219, 234, 254, 0.35)
        alt 请求合法
            rect rgba(220, 252, 231, 0.35)
                opt 需要补充校验
                    A->>B: 校验
                end
            end
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("层级标题", result.stderr)

    def test_transparent_rect_does_not_count_as_visual_distinction(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    rect rgba(219, 234, 254, 0.35)
        alt L1：请求合法
            rect transparent
                opt L2：需要补充校验
                    A->>B: 校验
                end
            end
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("有效背景色", result.stderr)

    def test_more_than_three_nested_regions_fail(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    rect rgba(219, 234, 254, 0.35)
        alt L1：一级
            rect rgba(220, 252, 231, 0.35)
                loop L2：二级
                    rect rgba(254, 243, 199, 0.35)
                        critical L3：三级
                            rect rgba(254, 226, 226, 0.35)
                                opt L4：四级
                                    A->>B: 调用
                                end
                            end
                        end
                    end
                end
            end
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("超过三层", result.stderr)

    def test_exception_semantic_marker_requires_red_rect(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    alt 调用成功
        A-->>B: 返回结果
    else 调用异常
        %% semantic:exception
        rect rgba(254, 243, 199, 0.35)
            A-->>B: 返回错误
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("异常语义必须使用红色系 rect", result.stderr)

    def test_fallback_semantic_marker_requires_yellow_rect(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    opt 启用兜底
        %% semantic:fallback
        rect rgba(254, 226, 226, 0.35)
            A->>B: 读取缓存
        end
    end
```
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("兜底语义必须使用黄色系 rect", result.stderr)

    def test_semantic_markers_with_matching_rect_colors_pass(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    rect rgba(219, 234, 254, 0.35)
        alt L1：调用成功
            A-->>B: 返回结果
        else L1：调用失败
            %% semantic:exception
            rect rgba(254, 226, 226, 0.35)
                A-->>B: 返回错误
            end
            %% semantic:fallback
            rect rgba(254, 243, 199, 0.35)
                opt L2：启用缓存兜底
                    A->>B: 读取缓存
                end
            end
        end
    end
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_ignores_other_mermaid_diagram_types_in_markdown(self) -> None:
        result = self.run_validator(
            """```mermaid
flowchart LR
    A --> B
```

```mermaid
sequenceDiagram
    autonumber
    A->>B: 请求
```
"""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("1 个图", result.stdout)

    def test_require_render_fails_without_mmdc(self) -> None:
        result = self.run_validator(
            """```mermaid
sequenceDiagram
    autonumber
    A->>B: 请求
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
            source.write_text(
                "sequenceDiagram\n    autonumber\n    A->>B: 请求\n",
                encoding="utf-8",
            )
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
