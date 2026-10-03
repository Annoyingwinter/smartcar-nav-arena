#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baseline_commander_stub —— 打榜框架占位节点, **不是任何参赛算法**。

这个文件是 smartcar-nav-arena 公开仓库里 `ucar_commander/scripts/commander.py`
的初始内容。它只做三件事:

    1. 提供 `/nav_start` 服务(计时器通过它发车);
    2. 收到发车指令后发一条机械臂归零指令;
    3. 然后**什么都不做**, 挂起等 Ctrl-C。

它不会规划、不会避障、不会下发 /cmd_vel。用它跑一轮 A0, 车会发完车
原地不动 —— 这是**故意**的: 它保证"零算法"基线, 也让任何人 clone 下来
5 分钟内就能验证自己的环境是通的(见 docs/DEPLOY.md 最后一节的端到端自测)。

参赛者要做的事: 把自己的算法写进本文件(或替换本文件), 然后
    bash harness/bench_run.sh <TAG> 2400
    python3 harness/bench_score.py <TAG>
细则允许你改动的只有:
    * 你提交的 commander 及其自建辅助文件
    * move_base / AMCL 的四个 config yaml 与 amcl.launch
详见 docs/RULES.md。

原始文件头(占位声明)
----------------------
本文件由仓库维护者(Space Bunny Free)在仓库初始化时创建, 用于替代任何
既有参赛实现。它不包含、也不复制任何其他模型的算法; 它的全部行为就是上面
三行。任何人都可以用它作为自己 commander.py 的起点。
"""
import rospy
from geometry_msgs.msg import Twist
from std_msgs.msg import String as StringMsg
from std_srvs.srv import SetBool, SetBoolResponse

ARM_ZERO_TOPIC = '/arm_control/move_to_pose'
ARM_ZERO_POSE = 'zero'


class BaselineStub(object):
    """占位: 只响应发车, 不导航。"""

    def __init__(self):
        self.arm_pub = rospy.Publisher(ARM_ZERO_TOPIC, StringMsg, queue_size=1)
        self._stop = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        self.service = rospy.Service('/nav_start', SetBool, self.nav_start_cb)
        rospy.loginfo(
            'baseline_commander_stub 已启动。'
            '这是打榜占位节点, 不含任何导航算法 —— 请在此实现你的 commander。')

    def nav_start_cb(self, req):
        """计时器点一下发车 -> 机械臂归零, 然后挂起。"""
        rospy.loginfo('收到发车指令, 发送机械臂归零 "%s" —— '
                      '本节点不做导航, 车会停在原地。', ARM_ZERO_POSE)
        try:
            self.arm_pub.publish(StringMsg(data=ARM_ZERO_POSE))
            # 发一个**全零** Twist 把车停住。刻意不给 .linear.x / .angular.z 赋值:
            # 那是"控制", 而占位桩必须不控制(仓库 CI 有形态检查盯着这一点)。
            # 但必须发停车指令 —— 否则发车后车靠惯性继续走, 与"它不导航"的说明对不上。
            self._stop.publish(Twist())
        except Exception as e:                                  # noqa: BLE001
            rospy.logwarn('下发归零指令失败: %s', e)
        return SetBoolResponse(success=True, message='baseline stub: no navigation')

    def spin(self):
        rospy.spin()


def main():
    rospy.init_node('baseline_commander_stub')
    BaselineStub().spin()


if __name__ == '__main__':
    main()