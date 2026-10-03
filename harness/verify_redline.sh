#!/usr/bin/env bash
# verify_redline.sh —— 核对红线组件有没有被改动
#
# 用法: bash harness/verify_redline.sh
# 退出码 0 = 全部一致; 1 = 有文件被改动(PR 会被打回)
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SHA=env/REDLINE_SHA.txt
fail=0
printf '%-62s %-17s %s\n' FILE EXPECTED ACTUAL
while read -r path want; do
    case "$path" in ''|\#*) continue ;; esac
    if [[ ! -f "$path" ]]; then
        printf '%-62s %-17s %s\n' "$path" "$want" "MISSING"; fail=1; continue
    fi
    got=$(sha256sum "$path" | cut -c1-16)
    if [[ "$got" == "$want" ]]; then
        printf '%-62s %-17s %s\n' "$path" "$want" "ok"
    else
        printf '%-62s %-17s %s   <== 被改动\n' "$path" "$want" "$got"; fail=1
    fi
done < "$SHA"

echo
if [[ $fail -eq 0 ]]; then
    echo "红线组件全部一致。"
else
    echo "!! 有红线组件被改动 —— 见 docs/RULES.md 第 1 节, PR 会被打回。"
fi
exit $fail
