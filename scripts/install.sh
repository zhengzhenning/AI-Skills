#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "用法: $0 <codex|claude|cursor|custom> <技能名>"
  echo "自定义目录: AI_SKILLS_TARGET_DIR=/path/to/skills $0 custom <技能名>"
}

if [[ $# -ne 2 ]]; then
  usage
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
  *)
    echo "错误: 不支持的工具 ${tool}。" >&2
    usage
    exit 2
    ;;
esac

if [[ ! -f "${source_dir}/SKILL.md" ]]; then
  echo "错误: 中央技能不存在或缺少 SKILL.md: ${source_dir}" >&2
  exit 1
fi

mkdir -p "${target_root}"
target_path="${target_root}/${skill_name}"

if [[ -L "${target_path}" ]]; then
  current_target="$(cd "$(dirname "${target_path}")" && cd "$(dirname "$(readlink "${target_path}")")" 2>/dev/null && pwd)/$(basename "$(readlink "${target_path}")")"
  if [[ "${current_target}" == "${source_dir}" ]]; then
    echo "已安装: ${target_path} -> ${source_dir}"
    exit 0
  fi
  echo "错误: 目标位置已有指向其他位置的软链接: ${target_path}" >&2
  exit 1
fi

if [[ -e "${target_path}" ]]; then
  echo "错误: 目标位置已有同名文件或目录，不会覆盖: ${target_path}" >&2
  exit 1
fi

ln -s "${source_dir}" "${target_path}"
echo "安装完成: ${target_path} -> ${source_dir}"
