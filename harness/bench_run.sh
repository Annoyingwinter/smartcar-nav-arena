#!/usr/bin/env bash
# 宿主机入口: 一轮打榜 = 摆锥桶(可选) + 起监视 + 进容器跑仿真 + 留产物
#
# 用法:
#   bash harness/bench_run.sh <TAG> [超时秒=2400] [锥桶列表"x,y;x,y"] [锥桶seed]
#
# 例:
#   bash harness/bench_run.sh my-A0 2400                              # 无锥轮
#   bash harness/bench_run.sh my-B2 2400 "1.419,-0.609;-0.653,-0.446;-0.422,0.892" 7
#
# 产物(全部落在仓库的 runs/ 下, 可直接作为提交证据):
#   runs/<TAG>/trace.csv                 5Hz 轨迹/锥桶距离采样
#   runs/sim_run_<TAG>.log               总控日志(起停仿真/发车/判定完赛)
#   runs/commander_<TAG>.log             你的 commander 的 stdout
#   runs/sim_nodes_<TAG>.log             导航栈节点 stderr
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/arena_env.sh"

TAG=${1:?用法: bench_run.sh <TAG> [超时秒] [锥桶列表] [seed]}
TIMEOUT=${2:-2400}
CONES=${3:-}
SEED=${4:-}

# ---------------------------------------------------------------------------
# 宿主侧路径 与 容器侧路径 是两套, 别混用。
#
#   BENCH      宿主视角的产物目录(给用户看、给 bench_score.py 读)
#   CR/BENCH_C 容器视角的同名目录(写进 PRE_RACE_CMD)
#
# 实测踩过的坑: 曾经 PRE_RACE 用宿主路径拼, 容器里 /home/<user>/... 是
# **另一个目录**(仓库实际挂在 /usr/local/share/arena_root), 于是监视节点把
# trace.csv 写进了容器自己的文件系统 —— 宿主上 runs/<TAG>/trace.csv 静默缺失,
# 而计分脚本只看"文件不存在", 于是 collisions 恒为 0, **看起来一切正常**。
# 一个不会报错、只会让碰撞罚消失的 bug, 比崩溃难查得多。
# 所以下面凡是进容器的路径, 一律用 CR 前缀。
# ---------------------------------------------------------------------------
CR="$ARENA_CONTAINER_ROOT"
BENCH="$ARENA_BENCH/$TAG"
BENCH_C="$CR/runs/$TAG"
mkdir -p "$BENCH"

# --- PRE_RACE: 在仿真起来之后、发车之前要做的事 ---
# 注意末尾的 `&`: 整条链在后台跑, 因为 spawn_cones 需要 nav_start 已就绪
# (它要往 gazebo 里插模型), 而监视节点要等 /clock。
PRE="mkdir -p '$BENCH_C'"
if [[ -n "$SEED" ]]; then
  PRE="$PRE && python3 '$CR/harness/spawn_cones.py' --seed $SEED"
fi
if [[ -n "$CONES" ]]; then
  # 摆锥脚本的结果与监视口径都以参数为准, 这里显式传给 commander,
  # 使"裁判知道锥桶在哪"与"算法知道锥桶在哪"用同一份数据。
  PRE="$PRE && rosparam set /ucar_commander/cones '$CONES'"
fi
PRE="$PRE && python3 '$CR/harness/bench_monitor.py' _cones:='$CONES' _out:='$BENCH_C/trace.csv' >/dev/null 2>&1 &"

# --- 进容器跑一轮仿真 ---
# 容器需已按 docs/DEPLOY.md 启动(默认名 $SMARTCAR_CONTAINER), 且把仓库
# bind mount 到 $ARENA_CONTAINER_ROOT(默认 /usr/local/share/arena_root)。
# 挂载点不同就改环境变量:
#   ARENA_CONTAINER_ROOT=/my/path bash harness/bench_run.sh ...
#
# 内层脚本用带引号的 heredoc 拼, 不做嵌套引号转义 —— 双层 bash -c 里塞引号
# 是这类脚本最常见的坏味道来源。
read -r -d '' INNER <<EOF || true
set -e
source '$CR/harness/arena_env.sh'
source /opt/ros/noetic/setup.bash
source '$CR/workspace/devel/setup.bash'
export PYTHONUNBUFFERED=1
bash '$CR/harness/run_sim.sh' $TIMEOUT
EOF

docker exec \
  -e PRE_RACE_CMD="$PRE" \
  -e RUN_TAG="$TAG" \
  -e ARENA_ROOT="$CR" \
  "$SMARTCAR_CONTAINER" bash -lc "$INNER"

# --- 产物自检: 少文件要当场说, 不能让计分脚本静默当成 0 分 ---
echo
missing=0
for f in "$ARENA_BENCH/sim_run_${TAG}.log" "$ARENA_BENCH/commander_${TAG}.log"; do
    if [[ -s "$f" ]]; then
        printf '  ✓ %s\n' "$f"
    else
        printf '  ✗ 缺失或为空: %s\n' "$f"; missing=1
    fi
done
# trace.csv 只在跑起来之后才有; 仿真起失败时 run_sim.sh 会自己报错退出。
if [[ -s "$BENCH/trace.csv" ]]; then
    printf '  ✓ %s (%s 行)\n' "$BENCH/trace.csv" "$(wc -l < "$BENCH/trace.csv")"
elif [[ -s "$ARENA_BENCH/sim_run_${TAG}.log" ]] && grep -q '发车!' "$ARENA_BENCH/sim_run_${TAG}.log"; then
    printf '  ✗ trace.csv 没生成 —— 监视节点没起来。这一轮的成绩不可信, 请看 sim_nodes 日志\n' \
        "      ($ARENA_BENCH/sim_nodes_${TAG}.log)"; missing=1
fi

echo
echo "计分: python3 harness/bench_score.py $TAG"
if [[ $missing -eq 1 ]]; then
    echo "!! 有产物缺失 —— 先解决再提交, 否则碰撞数会被当成 0(见 harness/bench_run.sh 顶部注释)"
    exit 1
fi