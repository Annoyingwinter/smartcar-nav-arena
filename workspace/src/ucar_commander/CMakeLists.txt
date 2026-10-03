cmake_minimum_required(VERSION 3.0.2)
project(ucar_commander)

## 编译 C++11
add_compile_options(-std=c++11)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  actionlib
  move_base_msgs
  std_srvs
  geometry_msgs
)

catkin_package(
  CATKIN_DEPENDS roscpp actionlib move_base_msgs std_srvs geometry_msgs
)

include_directories(
  ${catkin_INCLUDE_DIRS}
)

## 可执行文件：commander.cpp -> ucar_commander_node
add_executable(ucar_commander_node src/commander.cpp)
target_link_libraries(ucar_commander_node ${catkin_LIBRARIES})
add_dependencies(ucar_commander_node ${${PROJECT_NAME}_EXPORTED_TARGETS} ${catkin_EXPORTED_TARGETS})

## 如果需要安装
# install(TARGETS ucar_commander_node
#   ARCHIVE DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
#   LIBRARY DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION}
#   RUNTIME DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
# )