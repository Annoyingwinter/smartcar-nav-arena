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

# ---- 地图指针文件的参数必须与登记值一致 ----
# image 字段允许是相对文件名(建仓时从绝对路径改过来, 否则 clone 后 map_server
# 会去读仓库外的路径且**不报错**)。但 resolution/origin/阈值这五项决定地图内容,
# 一个字都不能动。
MAPYAML=workspace/src/ucar_navigation/maps/map.yaml
declare -A WANT=(
  [resolution]='0.050000'
  [negate]='0'
  [occupied_thresh]='0.65'
  [free_thresh]='0.196'
)
printf '\n%-62s %-17s %s\n' FILE EXPECTED ACTUAL
for k in resolution negate occupied_thresh free_thresh; do
    got=$(grep -E "^$k:" "$MAPYAML" | head -1 | sed 's/.*: *//' | tr -d ' ')
    if [[ "$got" == "${WANT[$k]}" ]]; then
        printf '%-62s %-17s %s\n' "$MAPYAML:$k" "${WANT[$k]}" ok
    else
        printf '%-62s %-17s %s   <== 被改动\n' "$MAPYAML:$k" "${WANT[$k]}" "$got"; fail=1
    fi
done
# origin 整体比对(带空格, 单独处理)
# 归一化必须对两边同时做(去空格), 否则 '[-5, -5, 0]' 与 '[-5,-5,0]' 会误判为不一致
want_org=$(echo '[-5.000000, -5.000000, 0.000000]' | tr -d ' ')
got_org=$(grep -E '^origin:' "$MAPYAML" | head -1 | sed 's/^origin: *//' | tr -d ' ')
if [[ "$got_org" == "$want_org" ]]; then
    printf '%-62s %-17s %s\n' "$MAPYAML:origin" '[-5,-5,0]' ok
else
    printf '%-62s %-17s %s   <== 被改动\n' "$MAPYAML:origin" '[-5,-5,0]' "$got_org"; fail=1
fi

# image 必须是相对路径, 且指向的文件真实存在
img=$(grep -E '^image:' "$MAPYAML" | head -1 | sed 's/^image: *//' | tr -d ' ')
imgdir=$(dirname "$MAPYAML")
if [[ "$img" == /* ]]; then
    printf '%-62s %-17s %s   <== 绝对路径, clone 到别的机器会失效\n' \
        "$MAPYAML:image" '(相对路径)' "$img"; fail=1
elif [[ ! -s "$imgdir/$img" ]]; then
    printf '%-62s %-17s %s   <== 指向的文件不存在\n' \
        "$MAPYAML:image" '(存在)' "$img"; fail=1
else
    printf '%-62s %-17s %s\n' "$MAPYAML:image" '(相对路径)' "ok -> $img"
fi

echo
if [[ $fail -eq 0 ]]; then
    echo "红线组件全部一致。"
else
    echo "!! 有红线组件被改动 —— 见 docs/RULES.md 第 1 节, PR 会被打回。"
fi
exit $fail
