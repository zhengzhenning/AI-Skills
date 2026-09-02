#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "用法: $0 <codex|claude|cursor|custom> <技能名>" >&2
  exit 2
fi

tool="$1"
skill_name="$2"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${root_dir}/skills/${skill_name}"

case "${tool}" in
  codex) target_root="${AI_SKILLS_TARGET_DIR:-${CODEX_HOME:-${HOME}/.codex}/skills}" ;;
  claude) target_root="${AI_SKILLS_TARGET_DIR:-${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/skills}" ;;
  cursor) target_root="${AI_SKILLS_TARGET_DIR:-${CURSOR_CONFIG_DIR:-${HOME}/.cursor}/skills}" ;;
  custom)
    if [[ -z "${AI_SKILLS_TARGET_DIR:-}" ]]; then
      echo "错误: custom 模式必须设置 AI_SKILLS_TARGET_DIR。" >&2
      exit 2
    fi
    target_root="${AI_SKILLS_TARGET_DIR}"
    ;;
  *) echo "错误: 不支持的工具 ${tool}。" >&2; exit 2 ;;
esac

target_path="${target_root}/${skill_name}"
if [[ ! -L "${target_path}" ]]; then
  echo "未卸载: 目标不是软链接或不存在: ${target_path}" >&2
  exit 1
fi

current_target="$(cd "$(dirname "${target_path}")" && cd "$(dirname "$(readlink "${target_path}")")" 2>/dev/null && pwd)/$(basename "$(readlink "${target_path}")")"
if [[ "${current_target}" != "${source_dir}" ]]; then
  echo "未卸载: 软链接不属于本中央仓库: ${target_path}" >&2
  exit 1
fi

rm "${target_path}"
echo "卸载完成，中央技能未删除: ${source_dir}"
