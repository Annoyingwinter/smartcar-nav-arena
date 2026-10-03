#!/usr/bin/env bash
# arena_env.sh —— 打榜工具链的唯一路径来源。所有 harness 脚本 source 它。
#
# 设计原则: **不硬编码任何绝对路径**。一切从本文件自身位置推导,
# 因此 `git clone` 到任何路径都能直接跑。
#
# 可用环境变量覆盖:
#   ARENA_ROOT           仓库根(默认: 本文件的上上级)。
#                        在宿主上跑 = 宿主路径; 在容器里跑 = 容器路径。
#   ARENA_CONTAINER_ROOT 仓库在**容器内**的挂载点
#                        (默认 /usr/local/share/arena_root)。只在宿主侧有意义。
#   SMARTCAR_CONTAINER   打榜容器名(默认 smartcar-bench)
#   ARENA_GAZEBO_MODEL_PATH  覆盖 GAZEBO_MODEL_PATH(必须指到 env/models)
#   ROS_MASTER_PORT     ROS master 端口(默认 11311)。仅在同宿主并行跑两轮时需要改;
#                       常规用法是串行跑轮, 不要动它。
#
# 宿主脚本(docker exec 那一侧)用 $ARENA_CONTAINER_ROOT 拼容器内路径,
# 并把它作为 ARENA_ROOT 传进容器; 容器内的脚本只认 $ARENA_ROOT。

set -euo pipefail

# --- 仓库根: harness/ 的上一级 ---
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ARENA_ROOT="${ARENA_ROOT:-$(cd "$_here/.." && pwd)}"

# --- 容器内看到的仓库根 ---
#
# 两个变量必须分开, 否则脚本在"宿主直接跑"和"docker exec 里跑"两种场景下
# 会互相串味:
#   ARENA_ROOT             本进程眼里的仓库根(宿主上是宿主路径, 容器里是容器路径)
#   ARENA_CONTAINER_ROOT   仓库在**容器内**的挂载点。只在宿主侧有意义,
#                          供 docker exec 时把路径翻译过去。
# 部署文档默认把仓库挂到 /usr/local/share/arena_root, 所以容器内可以完全
# 不看宿主路径 —— 这也是为什么 Dockerfile 的 entrypoint 与本文件都不该
# 出现任何个人家目录。
export ARENA_CONTAINER_ROOT="${ARENA_CONTAINER_ROOT:-/usr/local/share/arena_root}"
# ARENA_MOUNT 是 ARENA_ROOT 的别名, 保留它只是为了脚本里读起来更清楚。
export ARENA_MOUNT="$ARENA_ROOT"

export ARENA_HARNESS="$ARENA_ROOT/harness"
export ARENA_ENV="$ARENA_ROOT/env"
export ARENA_WS="$ARENA_ROOT/workspace"
export ARENA_MODELS="$ARENA_ENV/models"
export ARENA_BENCH="$ARENA_ROOT/runs"

export SMARTCAR_CONTAINER="${SMARTCAR_CONTAINER:-smartcar-bench}"
export SMARTCAR_WS_MOUNT="$ARENA_MOUNT/workspace"

# 容器内的 GAZEBO_MODEL_PATH(场地 mesh 全在这里, 缺了锥桶/场地就没碰撞)
#
# 这里**必须强制**赋值, 不能写成 ${GAZEBO_MODEL_PATH:-...}:
# 赛事参考镜像 smartcar-noetic-control:v2 把 GAZEBO_MODEL_PATH 烤死成了
# 它自己那套 models 目录, 而我们只把 env/models 挂了进来 —— 沿用镜像里的值
# 会指向一个不存在的目录, 结果是场地与锥桶**全部没有碰撞体**,
# 表现为「激光穿墙」「锥桶被撞飞」「地图和现实对不上」, 极难排查。
# 要换路径请用 ARENA_GAZEBO_MODEL_PATH, 语义更清楚。
if [[ -d "$ARENA_MODELS" ]]; then
    export GAZEBO_MODEL_PATH="${ARENA_GAZEBO_MODEL_PATH:-$ARENA_MODELS}"
elif [[ -z "${GAZEBO_MODEL_PATH:-}" ]]; then
    echo "!! 找不到 $ARENA_MODELS, 且 GAZEBO_MODEL_PATH 未设置" >&2
    echo "   场地 mesh 将无法加载 —— 检查 docker run 的 -v 挂载" >&2
fi

mkdir -p "$ARENA_BENCH"

# ---------------------------------------------------------------------------
# ROS 运行时环境(只在容器内设; 宿主上 source 本文件时保持不动)
#
# 为什么必须在**这里**再兜一次底, 而不是只靠容器 entrypoint:
# `docker exec` 起的是新进程, **不继承** entrypoint 里 export 的变量。
# 而 run_sim.sh 跑在 `set -u` 下, 引用一个未定义的 ROS_MASTER_URI 会直接
# 报 "unbound variable" 退出 —— 这是本仓库实测踩到的第一个坑。
#
# 为什么必须指回环: 容器用 --network host, 不显式指定时 ROS 会向广播地址
# 找 master, 表现为「节点全起来了但话题是空的」, 极难定位。
# ---------------------------------------------------------------------------
if [[ -f /opt/ros/noetic/setup.bash ]]; then
    # ROS_MASTER_PORT 用来把两轮仿真隔开。同一个宿主上同时跑两轮时(容器都用
    # --network host, 默认全抢 11311), 第二轮会静默地连到第一轮的 master 上,
    # 表现为「节点起了但话题空」「gazebo 起来了却等不到 /clock」。
    # 维护者本仓库实测踩过: 另一场并行的跑分把这一轮的仿真挤掉了。
    # 正确做法仍然是**串行跑轮**; 真要并行才设这个变量。
    export ROS_MASTER_PORT="${ROS_MASTER_PORT:-11311}"
    export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:$ROS_MASTER_PORT}"
    export ROS_HOSTNAME="${ROS_HOSTNAME:-127.0.0.1}"
    # 家目录没挂进容器, 写 ~/.ros 会 permission denied, 缓存/日志放 /tmp
    export ROS_HOME="${ROS_HOME:-/tmp/ros-home}"
    mkdir -p "$ROS_HOME" 2>/dev/null || true
fi