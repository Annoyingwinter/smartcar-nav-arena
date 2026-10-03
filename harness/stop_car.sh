#!/usr/bin/env bash
# 停车: 用零速度覆盖残留的 /cmd_vel
# (planar_move 插件会一直执行最后一条速度指令, teleop/脚本中途退出会留下残留转速)
rostopic pub -1 /cmd_vel geometry_msgs/Twist "{}" >/dev/null 2>&1 && echo "已停车"
