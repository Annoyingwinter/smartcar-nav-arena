#!/usr/bin/env bash
# bringup_container.sh —— 建镜像 + 起打榜容器(幂等: 已存在就复用)
#
# 用法:
#   bash harness/bringup_container.sh              # 建镜像 + 起容器
#   bash harness/bringup_container.sh --rebuild    # 强制重建镜像
#   bash harness/bringup_container.sh --down       # 停掉并删除容器
#
# 容器名默认 smartcar-bench(与历史打榜环境同名, 直接 docker start 也能复用)。
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/arena_env.sh"

IMAGE="${ARENA_IMAGE:-smartcar-nav-arena:noetic}"
CONTAINER="${SMARTCAR_CONTAINER:-smartcar-bench}"
GPU_FLAG=""
# 仓库在容器内的挂载点。与 arena_env.sh 的默认值一致。
CONTAINER_ROOT="$ARENA_CONTAINER_ROOT"

usage() { sed -n '2,10p' "$0"; exit 0; }
case "${1:-}" in
    --rebuild) REBUILD=1 ;;
    --down)
        echo "== 停掉并删除容器 $CONTAINER =="
        docker rm -f "$CONTAINER" 2>/dev/null || echo "(本来就不存在)"
        exit 0 ;;
    -h|--help) usage ;;
    "") REBUILD=0 ;;
    *) echo "未知参数: $1"; usage ;;
esac

# 有 NVIDIA 卡就带 --gpus all。RTF 从 ~0.3 升到 ~1.0,
# 但**计时用的是仿真秒**, 所以这只影响你等多久, 不影响成绩。
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    GPU_FLAG="--gpus all"
    echo "检测到 NVIDIA GPU, 启用 $GPU_FLAG"
else
    echo "未检测到 GPU, 走软渲染 (RTF≈0.1~0.3, 不影响计时口径)"
fi

if [[ "$REBUILD" == "1" ]]; then
    echo "== 重建镜像 $IMAGE =="
    docker build -f "$ARENA_HARNESS/Dockerfile" -t "$IMAGE" "$ARENA_HARNESS"
else
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        echo "== 镜像 $IMAGE 不存在, 开始构建(首次约 20~40 分钟) =="
        docker build -f "$ARENA_HARNESS/Dockerfile" -t "$IMAGE" "$ARENA_HARNESS"
    else
        echo "== 镜像 $IMAGE 已存在, 跳过构建(要重建加 --rebuild) =="
    fi
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    if [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER")" == "true" ]]; then
        echo "== 容器 $CONTAINER 已在运行, 复用 =="
    else
        echo "== 启动已有容器 $CONTAINER =="
        docker start "$CONTAINER" >/dev/null
    fi
else
    echo "== 创建容器 $CONTAINER =="
    # shellcheck disable=SC2086
    docker run -d --name "$CONTAINER" \
        --network host \
        --cpus 12 --memory 10g --shm-size 1g \
        $GPU_FLAG \
        --entrypoint /usr/local/bin/smartcar-entrypoint \
        -v "$ARENA_ROOT":"$CONTAINER_ROOT" \
        -v "$ARENA_HARNESS/smartcar-entrypoint.sh":/usr/local/bin/smartcar-entrypoint:ro \
        -e HOME=/tmp/flexhome \
        -e ARENA_ROOT="$CONTAINER_ROOT" \
        "$IMAGE" sleep infinity >/dev/null
fi

echo
echo "== 自检 =="
docker exec "$CONTAINER" bash -lc "
    source /opt/ros/noetic/setup.bash
    echo '  ROS_DISTRO   = \$ROS_DISTRO'
    echo '  gazebo       = ' \$(gazebo --version 2>&1 | head -1)
    for p in navigation amcl move_base map_server gmapping; do
        printf '  %-13s = %s\n' \"\$p\" \"\$(rospack find \$p >/dev/null 2>&1 && echo ok || echo MISSING)\"
    done
    echo '  GAZEBO_MODEL_PATH = \$GAZEBO_MODEL_PATH'
"

echo
echo "下一步: bash harness/build_workspace.sh"
echo "然后:   bash harness/bench_run.sh <TAG> 2400 && python3 harness/bench_score.py <TAG>"