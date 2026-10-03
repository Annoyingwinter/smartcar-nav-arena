#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按细则给一轮打榜结果计分.

用法: python3 harness/bench_score.py <TAG>

输入:
  runs/commander_<TAG>.log         决策节点日志(完赛判定/分段用时/统计)
  runs/bench/<TAG>/trace.csv       bench_monitor 轨迹(发车/兜袋/碰撞)
输出: 一行 JSON(便于拼进 leaderboard), 各分项按细则:

  成功发车        5 分   小车离开起点区域
  到达终点区域   10 分   停进终点兜袋 (x 1.40~2.087, y 0.61~1.08)
  选带锥桶地图    5 分   本轮摆了锥桶
  碰撞          -2/次   上限 -5; 监视为 0.30m 中心距代理, 标注"估算"
  白线外停车      0 / -2  在兜袋内=0; 出兜袋但完赛=-2 (按一轮估)
  时间得分      按名次    榜单只记仿真用时, 名次分赛场另计
"""
import csv
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POCKET = (1.40, 2.087, 0.61, 1.08)
START = (1.30, 2.10, 0.05, 0.65)


def in_box(x, y, b):
    return b[0] <= x <= b[1] and b[2] <= y <= b[3]


# 产物目录: 仓库的 runs/(宿主与容器 bind mount 同路径, 哪边跑都能读)。
# 可用 ARENA_BENCH 覆盖。
RUNDIR = os.environ.get('ARENA_BENCH') or os.path.join(
    os.path.dirname(HERE), 'runs')


def main(tag):
    cmdlog = os.path.join(RUNDIR, 'commander_%s.log' % tag)
    trace = os.path.join(RUNDIR, tag, 'trace.csv')
    res = dict(tag=tag, finished=False, sim_time=None, wall_time=None,
               depart=None, reach_final=None, collisions=0, pocket_stop=None,
               wp_time=[], stats={}, notes=[])
    if os.path.exists(cmdlog):
        txt = open(cmdlog, encoding='utf-8', errors='replace').read()
        m = re.search(r'完赛! 总用时 ([\d.]+) s', txt)
        if m:
            res['finished'] = True
            res['sim_time'] = float(m.group(1))
        else:
            res['notes'].append('未完赛(commander 中止或超时)')
        simlog_path = os.path.join(RUNDIR, 'sim_run_%s.log' % tag)
        m = re.search(r'耗时: 墙钟 ([\d.]+)s / 仿真 ([\d.]+|-?\d+\.\d+)s',
                      open(simlog_path, encoding='utf-8',
                           errors='replace').read()
                      if os.path.exists(simlog_path) else '')
        if m:
            res['wall_time'] = float(m.group(1))
        res['wp_time'] = [float(x) for x in
                          re.findall(r'到达航点 \d/\d .*?用时 ([\d.]+) s', txt)]
        m = re.search(r'重定位 (\d+) \| 清图 (\d+) \| 障碍层开关 (\d+)'
                      r'\s*\|\s*重试 (\d+) \| 停滞兜底 (\d+)', txt)
        if m:
            res['stats'] = dict(reloc=int(m.group(1)), clear=int(m.group(2)),
                                toggles=int(m.group(3)), retries=int(m.group(4)),
                                stalled=int(m.group(5)))
        if '静态模式' in txt:
            res['notes'].append('出现过静态模式降级')

    if os.path.exists(trace):
        rows = list(csv.DictReader(open(trace)))
        if rows:
            first, last = rows[0], rows[-1]
            fx, fy = float(last['x']), float(last['y'])
            res['pocket_stop'] = in_box(fx, fy, POCKET)
            res['final_xy'] = [round(fx, 3), round(fy, 3)]
            for r in rows:
                if r['cone_dist'] and float(r['cone_dist']) < 0.30:
                    res['collisions'] += 1
            # 碰撞按事件数计数(每行一个样本会重复计, 用列里的最近距粗算:
            # 连续 <0.30 的行合并为一次)
            eps, prev = 0, False
            res['collisions'] = 0
            for r in rows:
                cur = bool(r['cone_dist']) and float(r['cone_dist']) < 0.30
                if cur and not prev:
                    eps += 1
                prev = cur
            res['collisions'] = eps
            # 发车/完赛时刻(仿真秒, 相对监视器起点)
            for r in rows:
                if not in_box(float(r['x']), float(r['y']), START):
                    res['depart'] = float(r['t_sim'])
                    break
            if res['pocket_stop']:
                res['reach_final'] = True

    # ---- 计分 ----
    simlog = os.path.join(RUNDIR, 'sim_run_%s.log' % tag)
    has_cones = False
    if os.path.exists(simlog):
        has_cones = '已生成' in open(simlog, encoding='utf-8',
                                     errors='replace').read()
    s = dict(depart=5 if res['depart'] is not None else 0,
             final=10 if res['pocket_stop'] else 0,
             cones_map=5 if has_cones else 0, collision=0, line=0)
    if has_cones and not res['pocket_stop']:
        s['cones_map'] = 0  # 没停进兜袋谈不到"选带锥桶地图"的完整得分链
        res['notes'].append('未停进兜袋: 选图 5 分不计')
    if res['collisions']:
        s['collision'] = -min(2 * res['collisions'], 5)
    if res['finished'] and not res['pocket_stop']:
        s['line'] = -2
        res['notes'].append('完赛但未停进兜袋: 按一轮白线外估 -2')
    res['score'] = s
    res['subtotal'] = s['depart'] + s['final'] + s['cones_map'] + \
        s['collision'] + s['line']
    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main(sys.argv[1])
