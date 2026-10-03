#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按比赛细则随机摆放锥桶(测试用).

细则要求(北京科技大学第20届校内赛ROS组第一次分站赛细则):
  * 障碍物为红白相间锥桶, 随机摆放至起点到终点的路途中
  * 保证最小通过距离不小于小车宽度(手册实测口径: 约 0.5m 通过空间)
  * 数量不小于 3 个

本工具在 Gazebo 里生成静态锥桶, 每个位置都经过几何校验:
  * 只落在航线两侧(航线 = commander.py 的 ROUTE 航点序列, 两者必须同步)
  * 沿赛道法线方向实测更宽一侧的通过空间, >= --gap(默认 0.5m)才接受
  * 因此 0.48m 宽的北道会被自动排除 —— 与细则保证一致(车宽 0.342m,
    锥桶直径约 0.25m, 北道里放不下合法锥桶)
  * 相邻锥桶中心距 >= 1.0m, 避免多个锥桶粘连成不可通过的簇

用法(容器内, nav_start.launch 已启动之后、计时器 Draw 之前):
    python3 ~/smartcar/tools/spawn_cones.py                     # 默认摆 3 个
    python3 ~/smartcar/tools/spawn_cones.py -n 5                # 加大难度
    python3 ~/smartcar/tools/spawn_cones.py --seed 7            # 固定摆放, 复现用
    python3 ~/smartcar/tools/spawn_cones.py --gap 0.4           # 贴近细则下限(车宽0.342)
    python3 ~/smartcar/tools/spawn_cones.py --clear             # 只清掉已摆锥桶
    python3 ~/smartcar/tools/spawn_cones.py --dry-run           # 不连仿真, 纯几何
    python3 ~/smartcar/tools/spawn_cones.py --dry-run --plot /tmp/cones.png

红线: 建图(mapping.launch)阶段禁止摆锥桶 —— 会被建进静态地图, 之后
     每换一次锥桶位置图就作废一次。本工具检测到 gmapping 在跑时拒绝执行。
"""
import argparse
import math
import os
import random
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
# 场地世界文件: 仓库统一放一份在 env/round1.world(红线组件, 勿改)。
# 允许用 ARENA_ROOT / SCENARIO_WORLD 覆盖, 但**不要**指向自己的副本 ——
# 摆锥位置是按这个 world 的几何算出来的, 换 world 等于换了赛道。
_ROOT = os.environ.get('ARENA_ROOT') or os.path.dirname(HERE)
WORLD = os.environ.get('SCENARIO_WORLD') or os.path.join(
    _ROOT, 'env', 'round1.world')

# ---- 与 commander.py 的 ROUTE/出生点保持同步(2026-10-02 版) ----
SPAWN = (1.72, 0.27)
ROUTE = [
    (1.72, -0.75),   # 0 发车湾南下
    (0.20, -0.76),   # 1 南道向西
    (-0.75, -0.25),  # 2 西走廊
    (-0.35, 0.45),   # 3 西走廊上段
    (-0.15, 0.70),   # 4 弯向北道
    (0.50, 0.84),    # 5 进入北道
    (1.55, 0.87),    # 6 北道冲线
    (1.80, 0.85),    # 7 终点兜袋
]
LEG_NAMES = ["发车湾南下", "南道西行", "西走廊下段", "西走廊上段",
             "弯向北道", "北道入口", "北道直行", "终点兜袋"]

# ---- 几何常量 ----
R_CONE = 0.13          # 锥桶底半径(mesh 半径 0.126m, 取整留裕量), 激光面处更细
DEFAULT_GAP = 0.50     # 细则保证的通过空间(手册口径); 规则下限是车宽 0.342
CAR_WIDTH = 0.342
SPACING = 1.0          # 相邻锥桶最小中心距
STATION_STEP = 0.15    # 航线采样步长
START_OFFSET = 0.5     # 出生点后这段不摆(别把锥桶怼在出生点上)
LATERAL_MAX = 0.45     # 中心线两侧最大偏移
PROBES = 60            # 每个采样点最多尝试的横向偏移数
RAY_MAX = 3.0
MAX_N = 12

CONE_SDF = """<?xml version="1.0"?>
<sdf version="1.6">
  <model name="{name}">
    <static>true</static>
    <link name="link">
      <collision name="collision">
        <geometry>
          <mesh>
            <scale>5 5 5</scale>
            <uri>model://construction_cone/meshes/construction_cone.dae</uri>
          </mesh>
        </geometry>
      </collision>
      <visual name="visual">
        <geometry>
          <mesh>
            <scale>5 5 5</scale>
            <uri>model://construction_cone/meshes/construction_cone.dae</uri>
          </mesh>
        </geometry>
      </visual>
    </link>
  </model>
</sdf>"""


# ---------------------------------------------------------------- 世界几何

def _pose6(node):
    p = node.find('pose') if node is not None else None
    if p is None or not p.text:
        return (0.0, 0.0, 0.0)
    v = [float(t) for t in p.text.split()]
    return (v[0], v[1], v[5])          # x, y, yaw(弧度)


def parse_walls(world_path):
    """round1.world -> [(x, y, yaw, half_len, half_thick)]。

    与 tools/check_map_quality.py 同一套解析(取 link 自身 <pose>,
    忽略 <state> 快照), 该解析已被激光实测验证。"""
    out = []
    root = ET.parse(world_path).getroot()
    for m in root.iter('model'):
        if m.get('name') != 'r1map':
            continue
        mx, my, ma = _pose6(m)
        cm, sm = math.cos(ma), math.sin(ma)
        for l in m.iter('link'):
            b = l.find('.//box/size')
            if b is None:
                continue
            sz = [float(v) for v in b.text.split()]
            lx, ly, la = _pose6(l)
            a = ma + la
            out.append((
                mx + lx * cm - ly * sm,
                my + lx * sm + ly * cm,
                a, sz[0] / 2.0, sz[1] / 2.0))
    return out


def ray_hit(px, py, dx, dy, walls, max_d):
    """射线与全部墙体 OBB 求交, 返回最近命中距离(无命中返回 max_d)。"""
    best = max_d
    for (cx, cy, a, hl, ht) in walls:
        ca, sa = math.cos(a), math.sin(a)
        ox, oy = px - cx, py - cy
        ou = ox * ca + oy * sa          # 沿墙长
        ov = -ox * sa + oy * ca         # 沿墙厚
        ru = dx * ca + dy * sa
        rv = -dx * sa + dy * ca
        tu0, tu1 = -math.inf, math.inf
        ok = True
        for (o, r, half) in ((ou, ru, hl), (ov, rv, ht)):
            if abs(r) < 1e-9:
                if abs(o) > half:
                    ok = False
                    break
                continue
            t0, t1 = (-half - o) / r, (half - o) / r
            if t0 > t1:
                t0, t1 = t1, t0
            tu0, tu1 = max(tu0, t0), min(tu1, t1)
            if tu0 > tu1:
                ok = False
                break
        if ok and 0.0 < tu1 and tu0 < best:
            best = max(tu0, 0.0)
    return best


def corridor_half_widths(x, y, nx, ny, walls):
    """沿赛道法线 ±n 打射线, 返回 (正侧距离, 负侧距离)。"""
    return (ray_hit(x, y, nx, ny, walls, RAY_MAX),
            ray_hit(x, y, -nx, -ny, walls, RAY_MAX))


def point_wall_dist(x, y, walls):
    """点到最近墙面的距离(判"别放进墙里")。"""
    best = math.inf
    for (cx, cy, a, hl, ht) in walls:
        ca, sa = math.cos(a), math.sin(a)
        ox, oy = x - cx, y - cy
        u = ox * ca + oy * sa
        v = -ox * sa + oy * ca
        du = max(abs(u) - hl, 0.0)
        dv = max(abs(v) - ht, 0.0)
        best = min(best, math.hypot(du, dv))
    return best


# ---------------------------------------------------------------- 采样

def build_stations(walls):
    """沿航线按 STATION_STEP 采样, 返回 [(x, y, nx, ny, leg, arclen)]。"""
    pts = [SPAWN] + ROUTE
    stations = []
    arc = 0.0
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        dx, dy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -dy, dx                     # 法线
        d = START_OFFSET - arc if arc < START_OFFSET else STATION_STEP
        s = d
        while s < L:
            stations.append((x0 + dx * s, y0 + dy * s, nx, ny, i, arc + s))
            s += STATION_STEP
        arc += L
    return stations


def leg_normal_clearance(cx, cy, walls):
    """锥桶位置对**每一条** 0.6m 内经过的航段, 沿该航段法线实测两侧
    通道, 返回各航段 (leg, d+, d-)。

    只看锥桶所在航段会在弯角漏判: 弯角锥桶同时卡两条航段的通路
    (10-02 B1 实测: 湾口锥桶沿发车湾法线开阔, 但南道西行方向南北
    挤压仅 0.34m, 低于细则保证)。"""
    pts = [SPAWN] + ROUTE
    out = []
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        dx, dy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -dy, dx
        # 锥桶到该航段线段的距离
        t = max(0.0, min(L, (cx - x0) * dx + (cy - y0) * dy))
        px_, py_ = x0 + dx * t, y0 + dy * t
        if math.hypot(cx - px_, cy - py_) > 0.6:
            continue
        d1 = ray_hit(cx, cy, nx, ny, walls, RAY_MAX)
        d2 = ray_hit(cx, cy, -nx, -ny, walls, RAY_MAX)
        out.append((i, d1, d2))
    return out


def pick_spots(walls, n, seed, gap):
    """随机挑 n 个合法锥桶位。多轮重试取最优, 保证紧张场地也尽量摆满。
    返回 (spots 按 arclen 排序, 候选点总数)。"""
    stations = build_stations(walls)
    best = []
    for rnd in range(6):
        order = list(range(len(stations)))
        random.Random(seed + rnd * 7919).shuffle(order)
        rng = random.Random(seed * 31 + rnd * 104729)
        chosen = []
        for idx in order:
            if len(chosen) >= n:
                break
            x, y, nx, ny, leg, arc = stations[idx]
            for _ in range(PROBES):
                u = rng.uniform(-LATERAL_MAX, LATERAL_MAX)
                cx, cy = x + u * nx, y + u * ny
                # 可达性: 从中心线到探针点的路径不能穿墙 —— 否则锥桶会被
                # 放到墙背后(比如北道中线南侧穿过 Wall_20 放进封闭岛里)
                if abs(u) > 1e-6:
                    ux, uy = u * nx, u * ny
                    dist = math.hypot(ux, uy)
                    if ray_hit(x, y, ux / dist, uy / dist, walls,
                               dist + 0.01) < dist - 1e-6:
                        continue
                if point_wall_dist(cx, cy, walls) < R_CONE + 0.03:
                    continue
                # 多航段法线检查: 弯角锥桶同时受两条航段约束, 取最紧的
                legs = leg_normal_clearance(cx, cy, walls)
                if not legs:
                    continue
                passage, d1r, d2r = math.inf, 0.0, 0.0
                blocked = False
                for (_li, dd1, dd2) in legs:
                    # 两侧都必须打中实体墙: 场地外圈有缺口, 射线进空旷区
                    # 说明该点在赛道边界外, "通道"没有物理意义
                    if dd1 >= RAY_MAX or dd2 >= RAY_MAX:
                        blocked = True
                        break
                    p = max(dd1, dd2) - R_CONE
                    if p < passage:
                        passage, d1r, d2r = p, dd1, dd2
                if blocked or passage < gap:
                    continue
                if any(math.hypot(cx - c['x'], cy - c['y']) < SPACING
                       for c in chosen):
                    continue
                chosen.append(dict(x=cx, y=cy, d1=d1r, d2=d2r, passage=passage,
                                   leg=leg, arc=arc))
                break
        if len(chosen) > len(best):
            best = chosen
        if len(best) >= n:
            break
    best.sort(key=lambda c: c['arc'])
    return best, len(stations)


# ---------------------------------------------------------------- ROS 生成

def connect_ros():
    try:
        import rospy
        import rosnode
    except ImportError:
        sys.exit("容器里才能连仿真: 进容器后运行 "
                 "(bash ~/ros1_noetic/smartcar 再开终端)")
    return rospy, rosnode


def guard_mapping_phase(rosnode):
    try:
        nodes = rosnode.get_node_names()
    except Exception:
        return
    if any('gmapping' in n or 'slam_gmapping' in n for n in nodes):
        sys.exit("检测到 gmapping 在跑 —— 建图阶段禁止摆锥桶(会被建进静态地图)。"
                 "先结束建图并保存, 启动 nav_start.launch 之后再运行本工具。")


def clear_cones(rospy):
    try:
        rospy.wait_for_service('/gazebo/delete_model', timeout=15)
        delete = rospy.ServiceProxy('/gazebo/delete_model',
                                    __import__('gazebo_msgs.srv',
                                               fromlist=['DeleteModel'])
                                    .DeleteModel)
    except Exception as e:
        print("连接 /gazebo/delete_model 失败: %s" % e)
        return 0
    names = ['race_cone'] + ['race_cone_%d' % i for i in range(1, MAX_N + 1)]
    removed = 0
    for name in names:
        try:
            if delete(name).success:
                removed += 1
        except Exception:
            pass
    return removed


def spawn_cones(rospy, spots):
    from gazebo_msgs.srv import SpawnModel
    from geometry_msgs.msg import Pose, Quaternion
    try:
        rospy.wait_for_service('/gazebo/spawn_sdf_model', timeout=15)
        spawn = rospy.ServiceProxy('/gazebo/spawn_sdf_model', SpawnModel)
    except Exception as e:
        sys.exit("连接 /gazebo/spawn_sdf_model 失败: %s\n"
                 "请先启动 nav_start.launch(Gazebo 必须在跑)。" % e)
    ok = 0
    for i, c in enumerate(spots, 1):
        yaw = random.random() * 2 * math.pi
        q = Quaternion()
        q.z = math.sin(yaw / 2.0)
        q.w = math.cos(yaw / 2.0)
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = c['x'], c['y'], 0.0
        pose.orientation = q
        try:
            resp = spawn('race_cone_%d' % i, CONE_SDF.format(name='race_cone_%d' % i),
                         '', pose, 'world')
            if resp.success:
                ok += 1
            else:
                print("  锥桶%d 生成失败: %s" % (i, resp.status_message))
        except Exception as e:
            print("  锥桶%d 生成异常: %s" % (i, e))
    return ok


# ---------------------------------------------------------------- 输出

def report(spots, gap, seed, total_stations, n_requested):
    print("=" * 64)
    print("摆放方案 (gap>=%.2fm, seed=%s, 候选点 %d 个)" % (gap, seed, total_stations))
    print("-" * 64)
    for i, c in enumerate(spots, 1):
        print("锥桶%d  (%+.3f, %+.3f)  %-6s  两侧通道 %.2f/%.2fm  通过空间 %.2fm"
              % (i, c['x'], c['y'], LEG_NAMES[c['leg']],
                 c['d1'], c['d2'], c['passage']))
    if len(spots) < 3:
        print("警告: 细则要求锥桶数不小于 3, 当前只摆下 %d 个" % len(spots))
    elif len(spots) < n_requested:
        print("说明: 申请 %d 个只摆下 %d 个 —— gap=%.2f 下场地的合法位置"
              "就这么多; 想摆更多可降低 --gap (细则下限 %.3f)"
              % (n_requested, len(spots), gap, CAR_WIDTH))
    print("-" * 64)
    print("复现本次摆放: --seed %s" % seed)
    print("=" * 64)


def plot(spots, walls, path):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("(容器里没装 PIL, 跳过 --plot; 可在宿主机用 --dry-run --plot)")
        return
    X0, X1, Y0, Y1 = -2.0, 2.7, -2.0, 1.6
    SC = 240
    W, H = int((X1 - X0) * SC), int((Y1 - Y0) * SC)

    def px(x, y):
        return ((x - X0) * SC, (Y1 - y) * SC)

    img = Image.new('RGB', (W, H), 'white')
    dr = ImageDraw.Draw(img)
    for (cx, cy, a, hl, ht) in walls:
        ca, sa = math.cos(a), math.sin(a)
        corners = []
        for (du, dv) in ((hl, ht), (hl, -ht), (-hl, -ht), (-hl, ht)):
            corners.append(px(cx + du * ca - dv * sa, cy + du * sa + dv * ca))
        dr.polygon(corners, fill=(90, 90, 90))
    pts = [px(*p) for p in [SPAWN] + ROUTE]
    dr.line(pts, fill=(70, 130, 220), width=3)
    for (qx, qy) in pts:
        dr.ellipse([qx - 4, qy - 4, qx + 4, qy + 4], fill=(70, 130, 220))
    sx, sy = px(*SPAWN)
    dr.ellipse([sx - 7, sy - 7, sx + 7, sy + 7], outline=(0, 150, 0), width=4)
    for i, c in enumerate(spots, 1):
        cx, cy = px(c['x'], c['y'])
        r = R_CONE * SC
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(230, 60, 40),
                   outline=(120, 20, 10), width=2)
        dr.text((cx + r + 2, cy - 8), "#%d %.2fm" % (i, c['passage']),
                fill=(0, 0, 0))
    img.save(path)
    print("预览图已写入: %s" % path)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="按比赛细则随机摆放锥桶(测试用)")
    ap.add_argument('-n', '--num', type=int, default=3,
                    help="锥桶数量(细则要求 >=3, 默认 3)")
    ap.add_argument('--seed', type=float, default=None,
                    help="随机种子(不填则随机, 会打印出来供复现)")
    ap.add_argument('--gap', type=float, default=DEFAULT_GAP,
                    help="每个锥桶一侧最小通过空间, 默认 %.2fm (细则下限=车宽 %.3f)"
                         % (DEFAULT_GAP, CAR_WIDTH))
    ap.add_argument('--clear', action='store_true', help="只清掉已摆锥桶")
    ap.add_argument('--dry-run', action='store_true',
                    help="不连仿真, 只算摆放方案(可在宿主机跑)")
    ap.add_argument('--plot', metavar='PNG', help="把摆放方案画成图")
    ap.add_argument('--world', default=WORLD, help="round1.world 路径")
    args = ap.parse_args()

    if not os.path.exists(args.world):
        sys.exit("找不到世界文件: %s" % args.world)
    if args.num > MAX_N:
        sys.exit("一次最多摆 %d 个" % MAX_N)
    if args.gap < CAR_WIDTH:
        print("注意: --gap %.2f 低于车宽 %.3f, 车过不去, 已按 %.3f 处理"
              % (args.gap, CAR_WIDTH, CAR_WIDTH + 0.01))
        args.gap = CAR_WIDTH + 0.01
    seed = args.seed if args.seed is not None else random.randint(0, 10 ** 9)

    walls = parse_walls(args.world)

    if args.clear:
        rospy, rosnode = connect_ros()
        guard_mapping_phase(rosnode)
        removed = clear_cones(rospy)
        print("已清掉 %d 个旧锥桶" % removed)
        return

    spots, total = pick_spots(walls, args.num, seed, args.gap)
    report(spots, args.gap, seed, total, args.num)
    if args.plot:
        plot(spots, walls, args.plot)

    if args.dry_run:
        return

    rospy, rosnode = connect_ros()
    guard_mapping_phase(rosnode)
    removed = clear_cones(rospy)
    if removed:
        print("已清掉 %d 个旧锥桶" % removed)
    if args.clear:
        return
    if not spots:
        sys.exit("一个合法位置都找不到 —— 试试降低 --gap(细则下限 %.3f)"
                 % CAR_WIDTH)
    ok = spawn_cones(rospy, spots)
    print("已生成 %d/%d 个锥桶。摆完后照常: commander 就绪 -> 计时器 Draw"
          % (ok, len(spots)))
    if ok < args.num:
        print("没有摆够 %d 个: 候选位置不足, 可降低 --gap 或减少 -n 重跑"
              % args.num)
        sys.exit(2)


if __name__ == '__main__':
    main()
