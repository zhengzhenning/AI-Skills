#!/usr/bin/env python3
"""静态检查 Mermaid 时序图，并在可用时通过 mmdc 实际渲染。"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


MERMAID_FENCE = re.compile(
    r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
CONTROL_STARTS = {"alt", "opt", "loop", "par", "critical", "break", "rect", "box"}
LOGIC_REGIONS = {"alt", "opt", "loop", "par", "critical", "break"}
LEVEL_TITLE = re.compile(r"^L([1-3])[：:]\s*\S")
VISIBLE_RECT_COLOR = re.compile(r"^(?:rgba?\s*\(.+\)|hsla?\s*\(.+\)|[A-Za-z]+)$")
SEMANTIC_MARKER = re.compile(r"^%%\s*semantic:(exception|fallback)\s*$")
RGBA_COLOR = re.compile(
    r"^rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*\)$",
    re.IGNORECASE,
)
SEMANTIC_PALETTES = {
    "exception": {(254, 226, 226), (254, 202, 202), (254, 178, 178)},
    "fallback": {(254, 243, 199), (253, 230, 138), (252, 211, 77)},
}
SEMANTIC_NAMES = {"exception": "异常", "fallback": "兜底"}


def is_sequence_diagram(source: str) -> bool:
    """判断第一条有效语句是否声明为时序图。"""
    meaningful = [
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("%%")
    ]
    return bool(meaningful) and meaningful[0] == "sequenceDiagram"


def extract_diagrams(path: Path) -> list[tuple[str, str]]:
    """从 Markdown 或独立 Mermaid 文件中提取时序图。"""
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".mmd", ".mermaid"}:
        return [(path.name, content)]
    return [
        (f"{path.name}#{index}", match.group(1))
        for index, match in enumerate(MERMAID_FENCE.finditer(content), start=1)
        if is_sequence_diagram(match.group(1))
    ]


def matches_semantic_palette(color: str, semantic: str) -> bool:
    """判断 rect 是否使用规定的语义色系和低饱和透明度。"""
    match = RGBA_COLOR.fullmatch(color)
    if match is None:
        return False
    rgb = tuple(int(value) for value in match.groups()[:3])
    alpha = float(match.group(4))
    return rgb in SEMANTIC_PALETTES[semantic] and 0.25 <= alpha <= 0.40


def validate_static(label: str, source: str) -> list[str]:
    """检查图类型、控制块、区域区分和显式激活条。"""
    errors: list[str] = []
    lines = source.splitlines()
    meaningful = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("%%")]
    if not meaningful or meaningful[0] != "sequenceDiagram":
        errors.append(f"{label}: 第一条有效语句必须是 sequenceDiagram")
        return errors
    if len(meaningful) < 2 or meaningful[1] != "autonumber":
        errors.append(f"{label}: 第二条有效语句必须是 autonumber")

    controls: list[tuple[str, int, str | None]] = []
    regions: list[tuple[str, int, int, str, str | None]] = []
    activations: defaultdict[str, int] = defaultdict(int)
    pending_semantic: tuple[str, int] | None = None
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        marker = SEMANTIC_MARKER.fullmatch(line)
        if marker:
            if pending_semantic is not None:
                semantic, marker_line = pending_semantic
                errors.append(
                    f"{label}:{marker_line}: {SEMANTIC_NAMES[semantic]}语义标记后必须紧跟 rect"
                )
            pending_semantic = (marker.group(1), line_number)
            continue
        if line.startswith("%%"):
            continue
        keyword = line.split(maxsplit=1)[0]
        if pending_semantic is not None:
            semantic, marker_line = pending_semantic
            if keyword != "rect":
                errors.append(
                    f"{label}:{marker_line}: {SEMANTIC_NAMES[semantic]}语义标记后必须紧跟 rect"
                )
            else:
                color = line[len(keyword) :].strip()
                if not matches_semantic_palette(color, semantic):
                    color_name = "红色" if semantic == "exception" else "黄色"
                    errors.append(
                        f"{label}:{line_number}: {SEMANTIC_NAMES[semantic]}语义必须使用{color_name}系 rect"
                    )
            pending_semantic = None
        if keyword in CONTROL_STARTS:
            title = line[len(keyword) :].strip()
            rect_color = title if keyword == "rect" else None
            if keyword in LOGIC_REGIONS:
                depth = 1 + sum(control[0] in LOGIC_REGIONS for control in controls)
                parent_color = controls[-1][2] if controls and controls[-1][0] == "rect" else None
                regions.append((keyword, line_number, depth, title, parent_color))
            controls.append((keyword, line_number, rect_color))
        elif keyword == "end":
            if controls:
                controls.pop()
            else:
                errors.append(f"{label}:{line_number}: 出现没有对应控制块的 end")
        elif keyword == "else" and (not controls or controls[-1][0] != "alt"):
            errors.append(f"{label}:{line_number}: else 必须位于 alt 控制块内")
        elif keyword == "and" and (not controls or controls[-1][0] != "par"):
            errors.append(f"{label}:{line_number}: and 必须位于 par 控制块内")
        elif keyword == "option" and (not controls or controls[-1][0] != "critical"):
            errors.append(f"{label}:{line_number}: option 必须位于 critical 控制块内")

        activation = re.fullmatch(r"activate\s+(.+)", line)
        if activation:
            activations[activation.group(1)] += 1
        deactivation = re.fullmatch(r"deactivate\s+(.+)", line)
        if deactivation:
            actor = deactivation.group(1)
            if activations[actor] == 0:
                errors.append(f"{label}:{line_number}: {actor} 没有可结束的激活条")
            else:
                activations[actor] -= 1

    for keyword, line_number, _ in controls:
        errors.append(f"{label}:{line_number}: {keyword} 控制块未闭合")
    if pending_semantic is not None:
        semantic, marker_line = pending_semantic
        errors.append(
            f"{label}:{marker_line}: {SEMANTIC_NAMES[semantic]}语义标记后必须紧跟 rect"
        )

    if len(regions) > 1:
        missing_rect = [line_number for _, line_number, _, _, color in regions if color is None]
        if missing_rect:
            lines_text = "、".join(str(line_number) for line_number in missing_rect)
            errors.append(
                f"{label}: 多个逻辑区域块必须逐块使用独立 rect；缺失位置：{lines_text}"
            )

        invalid_color = [
            line_number
            for _, line_number, _, _, color in regions
            if color is not None
            and (color.lower() == "transparent" or VISIBLE_RECT_COLOR.fullmatch(color) is None)
        ]
        if invalid_color:
            lines_text = "、".join(str(line_number) for line_number in invalid_color)
            errors.append(f"{label}: 逻辑区域块的 rect 必须提供有效背景色；位置：{lines_text}")

        colors: dict[str, list[int]] = defaultdict(list)
        for _, line_number, _, _, color in regions:
            if color is not None:
                colors[color].append(line_number)
        duplicated = [positions for positions in colors.values() if len(positions) > 1]
        if duplicated:
            positions = "；".join("、".join(str(item) for item in group) for group in duplicated)
            errors.append(f"{label}: 逻辑区域块颜色不得重复；重复位置：{positions}")

    max_depth = max((depth for _, _, depth, _, _ in regions), default=0)
    if max_depth > 1:
        for keyword, line_number, depth, title, _ in regions:
            match = LEVEL_TITLE.match(title)
            if match is None or int(match.group(1)) != depth:
                errors.append(
                    f"{label}:{line_number}: 嵌套 {keyword} 必须使用 L{depth}：... 层级标题"
                )
    if max_depth > 3:
        errors.append(f"{label}: 逻辑区域块嵌套超过三层，必须拆图")

    for actor, count in activations.items():
        if count:
            errors.append(f"{label}: {actor} 有 {count} 个激活条未结束")
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
            errors.append(f"{path}: 没有找到 Mermaid 时序图")
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

    render_errors = [
        error
        for label, source in diagrams
        if (error := render_with_mmdc(label, source, mmdc)) is not None
    ]
    if render_errors:
        print("\n".join(render_errors), file=sys.stderr)
        return 1
    print(f"静态校验和实际渲染通过：{len(diagrams)} 个图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
