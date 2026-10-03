#!/usr/bin/env bash
# build_workspace.sh —— 在容器里编译 ROS 工作空间(catkin_make)
#
# 用法: bash harness/build_workspace.sh [catkin_make 参数, 默认 -j4]
#   bash harness/build_workspace.sh -j8
#
# 宿主机跑。内部的 docker exec 用 $ARENA_CONTAINER_ROOT(容器内挂载点)拼路径,
# 而不是宿主的 $ARENA_ROOT —— 默认部署下这两个根本不是同一个路径。
#
# 内层脚本用带引号的 heredoc 拼出来, 不做嵌套引号转义: 双层 bash -c 里塞
# 引号是这类脚本最常见的坏味道来源(改一次就悄悄坏掉)。
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/arena_env.sh"

JOBS="${1:--j4}"
CONTAINER="${SMARTCAR_CONTAINER:-smartcar-bench}"
CR="$ARENA_CONTAINER_ROOT"
WS="$CR/workspace"

echo "== 编译工作空间 ($JOBS) =="
echo "   宿主: $ARENA_ROOT/workspace"
echo "   容器: $WS"

read -r -d '' BUILD_SCRIPT <<EOF || true
set -e
source /opt/ros/noetic/setup.bash
cd '$WS'
# devel/ 与 build/ 是编译产物, 不进版本库。若上次编译是在不同依赖集下完成的,
# 残留缓存会报出很难懂的错, 所以先清掉再编。
rm -rf build devel
catkin_make $JOBS
EOF

docker exec -e ARENA_ROOT="$CR" "$CONTAINER" bash -lc "$BUILD_SCRIPT"

echo
echo "编译完成。验证一下容器内能看到什么:"
read -r -d '' VERIFY_SCRIPT <<EOF || true
source /opt/ros/noetic/setup.bash
# 也要 source arena_env.sh: 赛事参考镜像把 GAZEBO_MODEL_PATH 烤死成了它自己
# 那套 models 目录, 只有 arena_env.sh 会把它改指到本仓库的 env/models。
source '$CR/harness/arena_env.sh'
source '$WS/devel/setup.bash'
echo "  ARENA_ROOT           = \$ARENA_ROOT"
echo "  GAZEBO_MODEL_PATH    = \$GAZEBO_MODEL_PATH"
echo "  ucar_commander       = \$(rospack find ucar_commander)"
echo "  commander 可执行     = \$(command -v rosrun >/dev/null && ls '$WS/devel/lib/ucar_commander' 2>/dev/null | tr '\n' ' ')"
EOF

docker exec -e ARENA_ROOT="$CR" "$CONTAINER" bash -lc "$VERIFY_SCRIPT"

cat <<EOF

下一步: bash harness/bench_run.sh <TAG> 2400
       python3 harness/bench_score.py <TAG>
提示:   默认 commander 是**占位桩**, 车不会动, finished=false 属预期(见 DEPLOY.md 第 5 节)。
EOF