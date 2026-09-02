#!/usr/bin/env python3
"""静态检查 Mermaid 流程图，并在可用时通过 mmdc 实际渲染。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


MERMAID_FENCE = re.compile(
    r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
FLOWCHART_DECLARATION = re.compile(r"^(?:flowchart|graph)\s+(?:TB|TD|BT|LR|RL)$")
CLASS_DEF = re.compile(r"^classDef\s+([A-Za-z_][A-Za-z0-9_-]*)\s+(.+)$")
SEMANTIC_CLASS_USE = re.compile(r":::(exception|fallback)\b")
CLASS_ASSIGNMENT = re.compile(
    r"^class\s+([A-Za-z_][A-Za-z0-9_]*(?:,[A-Za-z_][A-Za-z0-9_]*)*)\s+"
    r"([A-Za-z_][A-Za-z0-9_-]*)\s*$"
)
SUBGRAPH_DECLARATION = re.compile(
    r"^subgraph\s+([A-Za-z_][A-Za-z0-9_]*)\[(.+)\]\s*$"
)
LEVEL_TITLE = re.compile(r"^L([1-3])[：:]\s*\S")
SEMANTIC_STYLES = {
    "exception": {"fill": "#fee2e2", "stroke": "#b91c1c", "color": "#7f1d1d"},
    "fallback": {"fill": "#fef3c7", "stroke": "#b45309", "color": "#78350f"},
}


def first_statement(source: str) -> str | None:
    """返回忽略空行和 Mermaid 注释后的第一条语句。"""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("%%"):
            return stripped
    return None


def is_flowchart(source: str) -> bool:
    """判断第一条有效语句是否声明为流程图。"""
    statement = first_statement(source)
    return statement is not None and FLOWCHART_DECLARATION.fullmatch(statement) is not None


def extract_diagrams(path: Path) -> list[tuple[str, str]]:
    """从 Markdown 或独立 Mermaid 文件中提取流程图。"""
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".mmd", ".mermaid"}:
        return [(path.name, content)]
    return [
        (f"{path.name}#{index}", match.group(1))
        for index, match in enumerate(MERMAID_FENCE.finditer(content), start=1)
        if is_flowchart(match.group(1))
    ]


def parse_style_properties(source: str) -> dict[str, str]:
    """解析 classDef 的逗号分隔样式属性。"""
    properties: dict[str, str] = {}
    for item in source.split(","):
        key, separator, value = item.partition(":")
        if separator:
            properties[key.strip().lower()] = value.strip().lower()
    return properties


def validate_static(label: str, source: str) -> list[str]:
    """检查图类型、子图闭合和子图内部方向语法。"""
    errors: list[str] = []
    statement = first_statement(source)
    if statement is None or FLOWCHART_DECLARATION.fullmatch(statement) is None:
        errors.append(f"{label}: 第一条有效语句必须是 flowchart/graph 和有效方向")
        return errors

    subgraphs: list[tuple[str | None, int, int, str]] = []
    regions: list[tuple[str | None, int, int, str]] = []
    class_definitions: dict[str, tuple[int, dict[str, str]]] = {}
    class_assignments: dict[str, str] = {}
    used_semantics: set[str] = set()
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("%%"):
            continue
        keyword = line.split(maxsplit=1)[0]
        used_semantics.update(SEMANTIC_CLASS_USE.findall(line))
        assignment = CLASS_ASSIGNMENT.fullmatch(line)
        if assignment:
            class_name = assignment.group(2)
            if class_name in SEMANTIC_STYLES:
                used_semantics.add(class_name)
            for item_id in assignment.group(1).split(","):
                class_assignments[item_id] = class_name
        class_def = CLASS_DEF.fullmatch(line)
        if class_def:
            class_definitions[class_def.group(1)] = (
                line_number,
                parse_style_properties(class_def.group(2)),
            )
        if keyword == "subgraph":
            declaration = SUBGRAPH_DECLARATION.fullmatch(line)
            region_id = declaration.group(1) if declaration else None
            title = declaration.group(2) if declaration else line[len("subgraph") :].strip()
            region = (region_id, line_number, len(subgraphs) + 1, title)
            subgraphs.append(region)
            regions.append(region)
        elif keyword == "end":
            if subgraphs:
                subgraphs.pop()
            else:
                errors.append(f"{label}:{line_number}: 出现没有对应 subgraph 的 end")
        elif keyword == "direction":
            parts = line.split()
            if not subgraphs:
                errors.append(f"{label}:{line_number}: direction 只能用于 subgraph 内部")
            elif len(parts) != 2 or parts[1] not in {"TB", "TD", "BT", "LR", "RL"}:
                errors.append(f"{label}:{line_number}: subgraph direction 无效")

    for _, line_number, _, _ in subgraphs:
        errors.append(f"{label}:{line_number}: subgraph 未闭合")
    for semantic in used_semantics:
        if semantic not in class_definitions:
            errors.append(f"{label}: 使用了 {semantic} 语义类但没有对应 classDef")
    for semantic, (line_number, properties) in class_definitions.items():
        if semantic not in SEMANTIC_STYLES:
            continue
        if any(properties.get(key) != value for key, value in SEMANTIC_STYLES[semantic].items()):
            color_name = "红色" if semantic == "exception" else "黄色"
            errors.append(f"{label}:{line_number}: {semantic} 必须使用规定的{color_name}系")

    if len(regions) > 1:
        missing_class = [
            line_number
            for region_id, line_number, _, _ in regions
            if region_id is None or region_id not in class_assignments
        ]
        if missing_class:
            positions = "、".join(str(item) for item in missing_class)
            errors.append(f"{label}: 每个区域必须使用独立的语义类；缺失位置：{positions}")

        assigned_classes = [
            class_assignments[region_id]
            for region_id, _, _, _ in regions
            if region_id is not None and region_id in class_assignments
        ]
        if len(assigned_classes) != len(set(assigned_classes)):
            errors.append(f"{label}: 不同区域不得复用同一个语义类")

        style_signatures: dict[tuple[tuple[str, str], ...], list[str]] = {}
        for class_name in assigned_classes:
            definition = class_definitions.get(class_name)
            if definition is None:
                errors.append(f"{label}: 区域语义类 {class_name} 缺少 classDef")
                continue
            signature = tuple(sorted(definition[1].items()))
            style_signatures.setdefault(signature, []).append(class_name)
        if any(len(class_names) > 1 for class_names in style_signatures.values()):
            errors.append(f"{label}: 不同区域的语义类不得复用完全相同的色值")

    max_depth = max((depth for _, _, depth, _ in regions), default=0)
    if max_depth > 1:
        for _, line_number, depth, title in regions:
            match = LEVEL_TITLE.match(title)
            if match is None or int(match.group(1)) != depth:
                errors.append(f"{label}:{line_number}: 嵌套 subgraph 必须使用 L{depth}：... 层级标题")
    if max_depth > 3:
        errors.append(f"{label}: subgraph 嵌套超过三层，必须拆图")
    return errors


def render_with_mmdc(label: str, source: str, mmdc: str) -> str | None:
    """使用 mmdc 渲染单个图，失败时返回错误信息。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "diagram.mmd"
        output_path = Path(temp_dir) / "diagram.svg"
        input_path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [mmdc, "-i", str(input_path), "-o", str(output_path)],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "未知渲染错误"
            return f"{label}: mmdc 渲染失败：{detail}"
        if not output_path.is_file() or output_path.stat().st_size == 0:
            return f"{label}: mmdc 返回成功但没有生成 SVG"
    return None


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Markdown、.mmd 或 .mermaid 文件")
    parser.add_argument("--require-render", action="store_true", help="缺少 mmdc 时返回失败")
    return parser.parse_args()


def main() -> int:
    """执行静态检查，并根据环境决定是否实际渲染。"""
    args = parse_args()
    diagrams: list[tuple[str, str]] = []
    errors: list[str] = []
    for path in args.files:
        if not path.is_file():
            errors.append(f"{path}: 文件不存在")
            continue
        extracted = extract_diagrams(path)
        if not extracted:
            errors.append(f"{path}: 没有找到 Mermaid 流程图")
            continue
        diagrams.extend((f"{path}:{label}", source) for label, source in extracted)

    for label, source in diagrams:
        errors.extend(validate_static(label, source))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    mmdc = shutil.which("mmdc")
    if mmdc is None:
        if args.require_render:
            print("未找到 mmdc，无法完成要求的实际渲染", file=sys.stderr)
            return 2
        print(f"静态校验通过：{len(diagrams)} 个图；未渲染验证（未找到 mmdc）")
        return 0

    render_errors: list[str] = []
    for label, source in diagrams:
        error = render_with_mmdc(label, source, mmdc)
        if error is not None:
            render_errors.append(error)
    if render_errors:
        print("\n".join(render_errors), file=sys.stderr)
        return 1
    print(f"静态校验和实际渲染通过：{len(diagrams)} 个图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
