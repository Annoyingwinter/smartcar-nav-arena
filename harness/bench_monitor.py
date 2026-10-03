#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打榜监视节点: 记录 /odom 轨迹、锥桶最近距离、发车/终点区状态 -> CSV.

细则的碰撞判定是裁判目判, 这里用车中心到锥桶中心的距离做代理:
  * 车矩形外接半径 0.214m + 锥桶底半径 0.13m -> 中心距 < 0.344 必然接触
  * 车半宽 0.128 + 0.13 = 0.258 (侧面蹭到)
  * 取 0.30m 为"疑似碰撞"阈值, 按事件去重(连续 <2s 算同一次), 榜单标注为估算

用 sim time(/clock); CSV 宿主机经 bind mount 直接可见。
"""
import csv
import math
import rospy
from nav_msgs.msg import Odometry

START_REGION = (1.30, 2.10, 0.05, 0.65)   # x0,x1,y0,y1 发车湾(离开即"发车")
POCKET = (1.40, 2.087, 0.61, 1.08)        # 终点兜袋
CONTACT_DIST = 0.30
SAMPLE_HZ = 5.0


def region_contains(x, y, r):
    return r[0] <= x <= r[1] and r[2] <= y <= r[3]


class Monitor(object):
    def __init__(self):
        cones = rospy.get_param('~cones', '')
        self.cones = []
        if cones.strip():
            for tok in cones.split(';'):
                xs, ys = tok.split(',')
                self.cones.append((float(xs), float(ys)))
        self.out = rospy.get_param('~out', '/tmp/trace.csv')
        self.pose = None
        self.rows = []
        self.left_start = None
        self.in_pocket = False
        self.contact = False
        self.contact_episodes = 0
        self.min_dists = [math.inf] * len(self.cones)
        rospy.Subscriber('/odom', Odometry, self.cb)
        rospy.on_shutdown(self.flush)

    def cb(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y),
                         1 - 2 * (q.y * q.y + q.z * q.z))
        self.pose = (p.x, p.y, yaw)

    def spin(self):
        rate = rospy.Rate(SAMPLE_HZ)
        while not rospy.is_shutdown():
            rate.sleep()
            if self.pose is None:
                continue
            t = rospy.get_time()
            x, y, yaw = self.pose
            # 最近锥桶
            dmin, cidx = math.inf, -1
            for i, (cx, cy) in enumerate(self.cones):
                d = math.hypot(x - cx, y - cy)
                if d < self.min_dists[i]:
                    self.min_dists[i] = d
                if d < dmin:
                    dmin, cidx = d, i
            if dmin < CONTACT_DIST and not self.contact:
                self.contact_episodes += 1
                rospy.logwarn("疑似碰撞 #%d: 距锥桶%d %.3fm (t=%.1fs)",
                              self.contact_episodes, cidx + 1, dmin, t)
            self.contact = dmin < CONTACT_DIST if self.cones else False
            # 发车判定: 离开发车湾
            if self.left_start is None and \
                    not region_contains(x, y, START_REGION):
                self.left_start = t
                rospy.loginfo("发车确认: 离开起点区域 (t=%.1fs)", t)
            self.in_pocket = region_contains(x, y, POCKET)
            self.rows.append((t, x, y, yaw, dmin if self.cones else '',
                              cidx + 1 if self.cones else '',
                              self.in_pocket))

    def flush(self):
        try:
            with open(self.out, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['t_sim', 'x', 'y', 'yaw', 'cone_dist',
                            'nearest_cone', 'in_pocket'])
                w.writerows(self.rows)
            rospy.loginfo("轨迹已写 %s (%d 行)", self.out, len(self.rows))
            if self.cones:
                for i, d in enumerate(self.min_dists, 1):
                    rospy.loginfo("锥桶%d 全程最近距离 %.3fm", i, d)
        except Exception as e:
            rospy.logerr("写 CSV 失败: %s", e)


if __name__ == '__main__':
    rospy.init_node('bench_monitor')
    Monitor().spin()
