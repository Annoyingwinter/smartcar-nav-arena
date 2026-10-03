# syntax=docker/dockerfile:1
#
# smartcar-nav-arena 打榜镜像
#
# 基础镜像固定 digest —— ROS Noetic / Ubuntu 20.04 都已结束标准支持, 用 tag 会
# 悄悄漂移到别的构建, 榜单就不可复现了。digest 取自赛事环境的部署记录:
#   osrf/ros@sha256:f138c82f326f179e8510eb03f40ee7ccaf16538e5577ab8550af74c4e12616de
#
# 说明: 本文件是**重建版**。赛事现场的参考镜像是 `smartcar-noetic-control:v2`,
# 它与本 Dockerfile 的差异我们没有拿到原始构建脚本; 已逐项核对过下面列的
# apt 包在参考镜像里全部存在。若你手头已有参考镜像, 直接用它也可以, 只要满足
# DEPLOY.md 第 8 节的三条即可。
FROM osrf/ros@sha256:f138c82f326f179e8510eb03f40ee7ccaf16538e5577ab8550af74c4e12616de

ARG DEBIAN_FRONTEND=noninteractive
ARG ROS_DISTRO=noetic

# --- 控制栈实际需要的包 ---
# navigation 是元包, 一次带齐 amcl / move_base / map_server / gmapping / dwa。
# gazebo_ros_pkgs 提供 gazebo 插件(小车 spawn、平面_move 里程计、关节控制器)。
# 显式列出是为了"少装一个就编不过"时能一眼看出缺谁。
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-${ROS_DISTRO}-navigation \
        ros-${ROS_DISTRO}-gmapping \
        ros-${ROS_DISTRO}-robot-state-publisher \
        ros-${ROS_DISTRO}-joint-state-publisher \
        ros-${ROS_DISTRO}-joint-state-publisher-gui \
        ros-${ROS_DISTRO}-teleop-twist-keyboard \
        ros-${ROS_DISTRO}-xacro \
        ros-${ROS_DISTRO}-gazebo-ros-pkgs \
        ros-${ROS_DISTRO}-gazebo-ros-control \
        ros-${ROS_DISTRO}-gazebo-plugins \
        ros-${ROS_DISTRO}-tf2-ros \
        ros-${ROS_DISTRO}-tf2-geometry-msgs \
        ros-${ROS_DISTRO}-laser-geometry \
        ros-${ROS_DISTRO}-image-transport \
        ros-${ROS_DISTRO}-cv-bridge \
        ros-${ROS_DISTRO}-rqt-robot-plugins \
        python3-colcon-common-extensions \
        python3-numpy \
        python3-pil \
        python3-yaml \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# --- 非 root 用户 + 免密 sudo ---
# 之所以要 sudo: gazebo/ros 首次运行要往 ~ 里写缓存, 而 rocker 风格的
# 镜像里家目录归 root。entrypoint 用 sudo -n 预建目录, 所以必须免密。
RUN useradd -m -u 1000 -s /bin/bash flexing \
    && echo 'flexing ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/flexing \
    && chmod 0440 /etc/sudoers.d/flexing

# --- 预建 gazebo/ros/rviz 需要可写的目录, 免得第一次起仿真就 permission denied ---
RUN mkdir -p /home/flexing/.gazebo /home/flexing/.ros /home/flexing/.rviz \
    && chown -R flexing:flexing /home/flexing

ENV HOME=/tmp/flexhome \
    ROS_DISTRO=noetic \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /home/flexing

# entrypoint 由 docker run 时 bind mount 覆盖(见 harness/smartcar-entrypoint.sh),
# 这里先放一份兜底, 保证 `docker run` 不带 -v 也能给出可读的错误提示。
COPY smartcar-entrypoint.sh /usr/local/bin/smartcar-entrypoint
RUN chmod +x /usr/local/bin/smartcar-entrypoint

ENTRYPOINT ["/usr/local/bin/smartcar-entrypoint"]
CMD ["sleep", "infinity"]