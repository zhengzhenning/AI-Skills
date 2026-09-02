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
echo "中央技能: ${source_dir}"
echo "安装位置: ${target_path}"

if [[ ! -f "${source_dir}/SKILL.md" ]]; then
  echo "状态: 中央技能不存在或不完整"
  exit 1
fi

if [[ -L "${target_path}" ]]; then
  echo "链接目标: $(readlink "${target_path}")"
  if [[ -e "${target_path}/SKILL.md" ]]; then
    echo "状态: 已安装且可用"
    exit 0
  fi
  echo "状态: 软链接已失效"
  exit 1
fi

if [[ -e "${target_path}" ]]; then
  echo "状态: 存在同名文件或目录，但不是中央技能软链接"
  exit 1
fi

echo "状态: 未安装"
exit 1
