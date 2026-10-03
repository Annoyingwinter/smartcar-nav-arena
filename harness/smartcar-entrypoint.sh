#!/usr/bin/env bash
# 打榜容器 entrypoint —— 由 docs/DEPLOY.md 的 docker run 挂成 /usr/local/bin/smartcar-entrypoint
#
# 干的事很少, 但每一条都是踩过坑的:
#   1. ROS_MASTER_URI / ROS_HOSTNAME 指回环 —— host network 下不指会互相广播;
#   2. ROS_HOME 放 /tmp —— 家目录没挂进容器, 写 ~/.ros 会 permission denied;
#   3. 预建并 chown ~/.gazebo ~/.ros ~/.rviz —— rocker 建的 /home/<user> 归 root,
#      gazebo 第一次跑要往里写, 不预建就起不来;
#   4. source ROS, 再 source catkin devel, 最后 cd 到工作空间 —— 顺序不能乱,
#      roslaunch 靠它解析 package 路径;
#   5. 路径全部来自 /usr/local/share/arena_root —— 仓库 bind mount 到哪,
#      这里就跟到哪, 不写死宿主路径。
set -Eeo pipefail

# --- 先导出, 再 source: ROS 的 profile 脚本会引用这些变量 ---
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_HOSTNAME="${ROS_HOSTNAME:-127.0.0.1}"

# 家目录未挂载进容器, ROS 缓存/日志必须放 /tmp
export ROS_HOME="${ROS_HOME:-/tmp/ros-home}"
mkdir -p "$ROS_HOME"

# rocker mkhomedir 建出的家目录归 root, 预建 Gazebo/ROS/RViz 需要可写的目录
sudo -n mkdir -p /home/flexing/.gazebo /home/flexing/.ros /home/flexing/.rviz 2>/dev/null || true
sudo -n chown -R "$(id -u):$(id -g)" \
    /home/flexing/.gazebo /home/flexing/.ros /home/flexing/.rviz 2>/dev/null || true

source /opt/ros/noetic/setup.bash

# --- 仓库根: 由 DEPLOY.md 用 -v <repo>:/usr/local/share/arena_root 挂进来 ---
ARENA_ROOT="${ARENA_ROOT:-/usr/local/share/arena_root}"
if [[ ! -d "$ARENA_ROOT" ]]; then
    echo "!! 找不到仓库根 $ARENA_ROOT" >&2
    echo "   docker run 时请加: -v \$(pwd):/usr/local/share/arena_root" >&2
    exit 1
fi
export ARENA_ROOT

smartcar_ws="$ARENA_ROOT/workspace"
if [[ -f "$smartcar_ws/devel/setup.bash" ]]; then
    source "$smartcar_ws/devel/setup.bash"
else
    # 注意: 这里**不能 exit**。
    # 部署顺序是「先起容器, 再编译工作空间」(见 docs/DEPLOY.md 第 2、3 节),
    # 所以第一次进来时 devel/ 必然不存在。这里只警告并把 ROS 环境准备好,
    # 让容器继续活着 —— 否则 build_workspace.sh 还没来得及跑, 容器就没了。
    echo "!! $smartcar_ws/devel/setup.bash 不存在 —— 工作空间还没编译。" >&2
    echo "   ROS 的 catkin 环境未加载; 请执行:" >&2
    echo "     bash harness/build_workspace.sh" >&2
    echo "   (或手动: cd '$smartcar_ws' && catkin_make)" >&2
fi

# GAZEBO_MODEL_PATH 必须指向本仓库的 env/models, 否则场地 mesh 与锥桶都没有碰撞体。
#
# 这里**强制**赋值。赛事参考镜像把这个变量烤死成了它自己那套 models 目录,
# 而我们只挂了本仓库的 env/models —— 沿用镜像里的值会指向不存在的目录,
# 表现为「激光穿墙 / 锥桶没有碰撞体 / 地图与现实对不上」。
# 要覆盖请用 ARENA_GAZEBO_MODEL_PATH。
if [[ -d "$ARENA_ROOT/env/models" ]]; then
    export GAZEBO_MODEL_PATH="${ARENA_GAZEBO_MODEL_PATH:-$ARENA_ROOT/env/models}"
fi

cd "$smartcar_ws"

if [[ $# -eq 0 ]]; then
    exec bash
fi
exec "$@"