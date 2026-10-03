cmake_minimum_required(VERSION 3.0.2)
project(ucar_bringup)

find_package(catkin REQUIRED)

catkin_package()

# 本包不编译任何代码, 只提供 launch 文件
# 文件只留在 src (devel/setup.bash 把 src 加入 ROS_PACKAGE_PATH, rospack find 解析到 src);
# 不要 install 到 share, 否则 roslaunch 报 "multiple files named"
