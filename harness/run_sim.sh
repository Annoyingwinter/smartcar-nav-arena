#!/usr/bin/env bash
# 在容器内跑一轮完整自主导航, 采集真实分段耗时。
# (通常不必直接调用: 宿主机用 bench_run.sh, 它会 docker exec 到这里)
#
# 路径全部来自 harness/arena_env.sh, 不硬编码。
# 产出: $ARENA_BENCH/sim_run_<TAG>.log (宿主同路径可见)
#
# 用法(容器内, 已 source 工作空间):
#   bash harness/run_sim.sh [超时秒]
set -uo pipefail

# commander 的 rospy.loginfo 走 stdout, 重定向到文件时是块缓冲的,
# 不加这个就得到进程退出才看到日志 —— 而我的完成判定是靠 grep 日志的
export PYTHONUNBUFFERED=1
export RCUTILS_LOGGING_BUFFERED=0

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/arena_env.sh"
LOGDIR="$ARENA_BENCH"
TAG="${RUN_TAG:-new}"
CMD="${RUN_CMD:-rosrun ucar_commander commander.py}"
LOG="$LOGDIR/sim_run_${TAG}.log"
CMDLOG="$LOGDIR/commander_${TAG}.log"
SIMLOG="$LOGDIR/sim_nodes_${TAG}.log"   # 按 TAG 隔离, 允许多个容器并行跑
TIMEOUT="${1:-600}"

: > "$LOG"
: > "$CMDLOG"
: > "$SIMLOG"

say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

cleanup() {
    say "收尾: 停掉所有节点"
    rosnode kill -a >/dev/null 2>&1
    pkill -f commander.py >/dev/null 2>&1
    pkill -f roslaunch >/dev/null 2>&1
    pkill -f gzserver >/dev/null 2>&1
    pkill -f gzclient >/dev/null 2>&1
    sleep 1
}
trap cleanup EXIT

# 等某个话题出现, 最多等 N 秒
wait_topic() {
    local topic="$1" limit="$2" i=0
    while [ $i -lt $((limit * 2)) ]; do
        if rostopic list 2>/dev/null | grep -qx "$topic"; then return 0; fi
        sleep 0.5; i=$((i + 1))
    done
    return 1
}

wait_service() {
    local svc="$1" limit="$2" i=0
    while [ $i -lt $((limit * 2)) ]; do
        if rosservice list 2>/dev/null | grep -qx "$svc"; then return 0; fi
        sleep 0.5; i=$((i + 1))
    done
    return 1
}

sim_now() { rostopic echo -n1 /clock 2>/dev/null | sed -n 's/.*secs[^0-9]*\([0-9.]*\).*/\1/p' | head -1; }

say "================ 开始一轮 [$TAG] (超时 ${TIMEOUT}s) ================"
say "ROS_DISTRO=$ROS_DISTRO"
say "决策节点: $CMD"

# 1) 拉起无头仿真 + 导航栈
# MAP 默认为考核在用的地图; 传绝对路径可切到候选地图做 A/B(不动任何默认件)
MAP="${MAP:-}"
say "拉起 headless_nav.launch (gazebo gui:=false, 不起 rviz)"
if [[ -n "$MAP" ]]; then
    say "  使用指定地图: $MAP"
    roslaunch "$ARENA_HARNESS/headless_nav.launch" gui:=false \
        map:="$MAP" > "$SIMLOG" 2>&1 &
else
    roslaunch "$ARENA_HARNESS/headless_nav.launch" gui:=false \
        > "$SIMLOG" 2>&1 &
fi
LAUNCH_PID=$!

if ! wait_topic /clock 120; then
    say "!! /clock 120s 内没出现, gazebo 可能没起来"
    say "---- sim_nodes.log 末尾 ----"
    tail -40 "$SIMLOG" | tee -a "$LOG"
    exit 1
fi
say "gazebo 起来了, use_sim_time=$(rosparam get /use_sim_time 2>/dev/null)"

if ! wait_topic /scan 90; then
    say "!! /scan 没出现, 激光/URDF 有问题"
    tail -40 "$SIMLOG" | tee -a "$LOG"
    exit 1
fi
say "激光就绪"

# /odom = planar_move 里程计起来了 = car3 真的在仿真里动
if ! wait_topic /odom 90; then
    say "!! /odom 没出现, car3 没被 spawn 出来"
    tail -40 "$SIMLOG" | tee -a "$LOG"
    exit 1
fi
say "里程计就绪"

# /amcl_pose = AMCL 真的在发 = map_server + amcl + move_base 整个栈活了
if ! wait_topic /amcl_pose 90; then
    say "!! /amcl_pose 没出现, 导航栈没起来"
    tail -40 "$SIMLOG" | tee -a "$LOG"
    exit 1
fi
say "导航栈就绪"

# 2) 起 commander
say "启动决策节点"
eval "$CMD" > "$CMDLOG" 2>&1 &
CMD_PID=$!
sleep 4
if ! kill -0 "$CMD_PID" 2>/dev/null; then
    say "!! commander 启动即挂"
    cat "$CMDLOG" | tee -a "$LOG"
    exit 1
fi
say "commander 存活, 等它注册 /nav_start 服务"
if ! wait_service /nav_start 40; then
    say "!! /nav_start 服务没注册, commander 卡在连 move_base"
    cat "$CMDLOG" | tee -a "$LOG"
    exit 1
fi
say "/nav_start 服务就绪"

# 3) 等机械臂归位(手册: 启动后约 3s), 然后发车
# 发车前钩子(打榜用): 摆锥桶/起监视器等, 在 /nav_start 就绪后、发车前执行
PRE_RACE_CMD="${PRE_RACE_CMD:-}"
if [[ -n "$PRE_RACE_CMD" ]]; then
    say "PRE_RACE: $PRE_RACE_CMD"
    eval "$PRE_RACE_CMD" >> "$LOG" 2>&1
    say "PRE_RACE 完成"
fi
say "等机械臂归位 5s"
sleep 5

T_SIM_START=$(sim_now)
W_START=$(date +%s.%N)
say "发车! sim_now=${T_SIM_START:-?}"
rosservice call /nav_start "data: true" 2>&1 | tee -a "$LOG"

# 4) 等 commander 报完赛
DONE=0
for i in $(seq 1 $((TIMEOUT * 2))); do
    if grep -qE "完赛|任务中止" "$CMDLOG" 2>/dev/null; then DONE=1; break; fi
    if ! kill -0 "$CMD_PID" 2>/dev/null; then say "决策节点进程退出"; break; fi
    sleep 0.5
done

W_END=$(date +%s.%N)
T_SIM_END=$(sim_now)
say "耗时: 墙钟 $(awk "BEGIN{printf \"%.1f\", $W_END - $W_START}")s / 仿真 $(awk "BEGIN{printf \"%.1f\", ${T_SIM_END:-0} - ${T_SIM_START:-0}}")s"

# 5) 最终位姿 (判断是否真到兜袋)
PX=$(rostopic echo -n1 /odom 2>/dev/null | sed -n 's/^position:.*//p' >/dev/null; \
     rostopic echo -n1 /amcl_pose/pose/pose/position 2>/dev/null | sed -n 's/^ *[xy]: *//p' | tr '\n' ' ')
say "最终 amcl 位置: ${PX:-取不到}"

say "---- commander 完整日志 ----"
cat "$CMDLOG" | tee -a "$LOG"

if [ "$DONE" = "1" ] && grep -q "完赛" "$CMDLOG"; then
    say "================ 本轮成功 ================"
else
    say "================ 本轮未完赛 ================"
fi
exit 0
