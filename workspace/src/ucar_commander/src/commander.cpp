#include <ros/ros.h>
#include <actionlib/client/simple_action_client.h>
#include <move_base_msgs/MoveBaseAction.h>
#include <geometry_msgs/Pose.h>
#include <geometry_msgs/PoseStamped.h>
#include <std_srvs/SetBool.h>

// 当前代码仅为参考模板，具体变量、功能函数有待选手自行实现

typedef actionlib::SimpleActionClient<move_base_msgs::MoveBaseAction> MoveBaseClient;

class UCarCommander
{
public:
    UCarCommander()
    {
        ros::NodeHandle nh;

        // 创建 move_base 客户端 用来获取 move_base 发布的消息
        client_ = new MoveBaseClient("move_base", true);
        // 等待客户端连接 如果没有等待会导致后续决策无法与 move_base 通信
        ROS_INFO("等待 move_base action server...");
        client_->waitForServer();
        ROS_INFO("move_base action server已连接 ");

        // 目标点信息参数
        goal_num_ = 0;
        // 目标点位置
        goal_point_position_ = geometry_msgs::Pose().position;
        // 目标点姿态
        goal_point_orientation_ = geometry_msgs::Pose().orientation;

        // 小车导航状态参数
        nav_start_ = false;  // 用来判断是否启动小车
        stage_ = 0;          // 当前导航状态

        // 计时器唤醒服务
        // 说明：计时器会向 '/nav_start' 发送服务请求，请求的 data=1
        service_ = nh.advertiseService("/nav_start", &UCarCommander::navStartCallback, this);
    }

    bool navStartCallback(std_srvs::SetBool::Request &req,
                          std_srvs::SetBool::Response &res)
    {
        // 这部分是服务回调函数 用来反馈计时器 service 的响应处理决策
        if (req.data)
        {
            // TODO: pass
        }
        else
        {
            // TODO: pass
        }
        return true;
    }

    void sendGoal(const geometry_msgs::Point &pos, const geometry_msgs::Quaternion &ori)
    {
        // 构建导航信息
        move_base_msgs::MoveBaseGoal goal;

        // TODO: pass

        // 通过服务发给
        client_->sendGoal(goal);

        // 等待 move_base 返回导航结果（此时整个决策代码流程阻塞直至导航有结果）
        client_->waitForResult();
        
        // 获得 move_base 导航结果
        if (client_->getState() == actionlib::SimpleClientGoalState::SUCCEEDED)
        {
            // TODO: pass
        }
        else
        {
            // TODO: pass
        }
    }

    void run()
    {
        // 主决策函数部分 用来状态控制切换 处理导航逻辑
        ros::Rate rate(10);
        while (ros::ok())
        {
            // TODO: pass
            ros::spinOnce();
            rate.sleep();
        }
    }

private:
    MoveBaseClient *client_;

    // 目标点信息参数
    int goal_num_;
    // 目标点位置
    geometry_msgs::Point goal_point_position_;
    // 目标点姿态
    geometry_msgs::Quaternion goal_point_orientation_;

    // 小车导航状态参数
    bool nav_start_;  // 用来判断是否启动小车
    int stage_;       // 当前导航状态

    // 计时器唤醒服务
    ros::ServiceServer service_;
};

int main(int argc, char **argv)
{
    ros::init(argc, argv, "ucar_commander_node");
    UCarCommander commander;
    commander.run();
    return 0;
}