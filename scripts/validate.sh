#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "用法: $0 <技能名>" >&2
  exit 2
fi

skill_name="$1"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skill_dir="${root_dir}/skills/${skill_name}"
skill_file="${skill_dir}/SKILL.md"
openai_file="${skill_dir}/agents/openai.yaml"

if [[ ! "${skill_name}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "错误: 技能名只能使用小写字母、数字和单个连字符分隔。" >&2
  exit 1
fi

if [[ ! -f "${skill_file}" ]]; then
  echo "错误: 缺少 ${skill_file}" >&2
  exit 1
fi

if [[ "$(head -n 1 "${skill_file}")" != "---" ]]; then
  echo "错误: SKILL.md 缺少 YAML frontmatter。" >&2
  exit 1
fi

frontmatter="$(awk 'NR == 1 { next } /^---[[:space:]]*$/ { exit } { print }' "${skill_file}")"
if ! grep -Eq "^name:[[:space:]]*${skill_name}[[:space:]]*$" <<<"${frontmatter}"; then
  echo "错误: frontmatter 中的 name 与目录名不一致。" >&2
  exit 1
fi
if ! grep -Eq '^description:[[:space:]]*.+$' <<<"${frontmatter}"; then
  echo "错误: frontmatter 缺少 description。" >&2
  exit 1
fi

if [[ -f "${openai_file}" ]]; then
  if ! grep -Eq '^[[:space:]]*allow_implicit_invocation:[[:space:]]*false[[:space:]]*$' "${openai_file}"; then
    echo "错误: openai.yaml 未明确关闭隐式触发。" >&2
    exit 1
  fi
  if ! grep -Fq "\$${skill_name}" "${openai_file}"; then
    echo "错误: openai.yaml 的默认提示未明确引用技能名。" >&2
    exit 1
  fi
fi

while IFS= read -r script; do
  bash -n "${script}"
done < <(find "${skill_dir}/scripts" -type f -name '*.sh' 2>/dev/null || true)

validator="${CODEX_HOME:-${HOME}/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
if [[ -f "${validator}" ]] && python3 -c 'import yaml' >/dev/null 2>&1; then
  python3 "${validator}" "${skill_dir}"
  echo "校验通过（包含 Codex 官方校验）。"
else
  echo "基础校验通过。未执行 Codex 官方校验：本机缺少校验器或 Python YAML 依赖。"
fi
