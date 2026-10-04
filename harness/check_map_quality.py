#!/usr/bin/env python3
"""建图质量验收: 建完图当场跑, 3 秒判断这张图能不能用于导航.

为什么要它
----------
考核流程里"现场建图"占 5 分, 但这张图同时决定后面 25 分导航能不能跑。
踩过的坑(实测现有 map.pgm):
  1. 只跑了一小圈 -> 全图 90% 是 unknown
  2. 建完又"修图"(刷白 + 擦幽灵墙) -> **把真墙当幽灵墙擦掉了**
所以建完图必须验一遍, 而不是"看着像就行"。

它怎么判
--------
用 round1.world 的**真实几何**当标准答案, 逐墙核对:
  * 覆盖率: 真实墙栅格里有多少被地图标成占据
  * unknown 比例: 越高越危险(track_unknown_space=true 时 = 致命障碍)
  * 幽灵墙: 地图标占据但真几何是空地的格子
  * 航点连通性: 按车体尺寸, 8 个航点能不能从出生点依次走到
最后给 PASS / WARN / FAIL, 以及具体该补哪块。

用法(容器内外都行, 只需 python3+numpy+PIL):
    python3 tools/check_map_quality.py                       # 查考核默认地图
    python3 tools/check_map_quality.py 某张图.pgm 某张图.yaml
只读, 不修改任何文件。
"""
import math
import os
import sys
import xml.etree.ElementTree as ET
from collections import deque

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# 建图验收: 拿"真几何"(round1.world)去比对建出来的图, 检查墙位误差。
# 路径来自仓库布局, 可用 ARENA_ROOT 覆盖。
_ROOT = os.environ.get('ARENA_ROOT') or os.path.dirname(HERE)
WS = os.path.join(_ROOT, 'workspace')
WORLD = os.environ.get('SCENARIO_WORLD') or os.path.join(_ROOT, 'env',
                                                       'round1.world')
DEFAULT_MAP = os.path.join(WS, 'src', 'ucar_navigation', 'maps', 'map.pgm')
DEFAULT_YAML = DEFAULT_MAP[:-4] + '.yaml'

SPAWN = (1.72, 0.27)
ROUTE = [(1.72, -0.75), (0.20, -0.76), (-0.75, -0.25), (-0.35, 0.45),
         (-0.15, 0.70), (0.50, 0.84), (1.55, 0.87), (1.80, 0.85)]
HALF_L, HALF_W = 0.171, 0.128
R_CIRC = math.hypot(HALF_L, HALF_W)   # 外接 0.213, 原地转向需要
R_CIRC_IN = min(HALF_L, HALF_W)      # 内切 0.128, 能过窄道的判据


def parse_yaml(path):
    d = {}
    with open(path) as f:
        for line in f:
            if ':' not in line or line.strip().startswith('#'):
                continue
            k, v = line.split(':', 1)
            d[k.strip()] = v.strip()
    img = d.get('image', 'map.pgm')
    res = float(d.get('resolution', 0.05))
    org = [float(t) for t in d.get('origin', '[-5,-5,0]').strip('[]').split(',')]
    d['_image'] = img if os.path.isabs(img) else os.path.join(os.path.dirname(path), img)
    d['_res'], d['_origin'] = res, (org[0], org[1])
    d['_occ'] = float(d.get('occupied_thresh', 0.65))
    d['_free'] = float(d.get('free_thresh', 0.196))
    return d


def pose(n):
    p = n.find('pose') if n is not None else None
    return np.zeros(6) if (p is None or not p.text) else \
        np.array([float(v) for v in p.text.split()])


def walls():
    out = []
    for m in ET.parse(WORLD).getroot().iter('model'):
        if m.get('name') != 'r1map':
            continue
        mp = pose(m)
        model_a = mp[5]  # SDF pose yaw already radians
        for l in m.iter('link'):
            b = l.find('.//box/size')
            if b is None:
                continue
            lp = pose(l)
            sz = [float(v) for v in b.text.split()]
            wall_a = model_a + lp[5]
            out.append((l.get('name'),
                        mp[0] + lp[0] * math.cos(model_a) - lp[1] * math.sin(model_a),
                        mp[1] + lp[0] * math.sin(model_a) + lp[1] * math.cos(model_a),
                        sz[0], sz[1], wall_a))
    return out


def to_px(x, y, h, w, res, origin):
    return (int(round((x - origin[0]) / res)),
            (h - 1) - int(round((y - origin[1]) / res)))


def wall_mask(segs, h, w, res, origin, *, cell_tolerance=True):
    """真实墙栅格。墙只有 3cm 厚, 而栅格 5cm —— 单格采样会漏掉大半,
    所以要把每个栅格中心到墙线段的距离算出来再判定, 而不是沿线打点。"""
    m = np.zeros((h, w), bool)
    half = 0.015 + (0.5 * res if cell_tolerance else 0.0)
    xs = origin[0] + np.arange(w) * res
    ys = origin[1] + (h - 1 - np.arange(h)) * res
    X, Y = np.meshgrid(xs, ys)              # X: [h, w]
    for (_n, x, y, L, T, a) in segs:
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = X - x, Y - y
        u = dx * ca + dy * sa              # 沿墙长
        v = -dx * sa + dy * ca             # 沿墙厚
        du = np.maximum(np.abs(u) - L / 2, 0.0)
        dv = np.maximum(np.abs(v) - T / 2, 0.0)
        m |= (np.hypot(du, dv) <= half)
    return m


def dilate(mask, r):
    if r <= 0:
        return mask.copy()
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def _unused_reachable(free, pts, radius):
    h, w = free.shape
    res = None
    nav = ~dilate(~free, 0)
    return None


def bfs_free(free, src, res, origin, radius_m):
    h, w = free.shape
    r = int(round(radius_m / res))
    nav = ~dilate(~free, r)
    sx, sy = to_px(src[0], src[1], h, w, res, origin)
    if not (0 <= sx < w and 0 <= sy < h) or not nav[sy, sx]:
        return None
    seen = np.zeros((h, w), bool)
    q = deque([(sy, sx)])
    seen[sy, sx] = True
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and nav[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return seen, nav


def main():
    pgm = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAP
    yaml = sys.argv[2] if len(sys.argv) > 2 else (DEFAULT_YAML
                                                 if pgm == DEFAULT_MAP
                                                 else os.path.splitext(pgm)[0] + '.yaml')
    print("=" * 68)
    print("建图质量验收")
    print("  图: %s" % pgm)
    print("  描述: %s" % yaml)
    if not os.path.exists(yaml):
        print("  !! 找不到同名 .yaml, 无法确定分辨率/原点, 无法验收")
        return 2
    cfg = parse_yaml(yaml)
    res, origin, occ_th, free_th = cfg['_res'], cfg['_origin'], cfg['_occ'], cfg['_free']
    img = np.asarray(Image.open(cfg['_image']).convert('L')).astype(np.float32) / 255.0
    h, w = img.shape
    print("  分辨率 %.3f  原点 %s  尺寸 %dx%d (= %.1fm x %.1fm)"
          % (res, origin, w, h, w * res, h * res))
    print()

    occ = (1.0 - img) >= occ_th  # map_server negate: 0 semantics
    occ_prob = 1.0 - img
    unk = (occ_prob < occ_th) & (occ_prob > free_th)
    segs = walls()
    truth_strict = wall_mask(segs, h, w, res, origin, cell_tolerance=False)
    truth_tolerant = wall_mask(segs, h, w, res, origin, cell_tolerance=True)

    tot = occ.size
    pct_unk = 100.0 * unk.sum() / tot
    tp = int((truth_strict & occ).sum())
    fn = int((truth_strict & ~occ).sum())
    fp = int((~truth_strict & occ).sum())
    cov = 100.0 * tp / max(1, truth_strict.sum())
    tolerant_tp = int((truth_tolerant & occ).sum())
    tolerant_cov = 100.0 * tolerant_tp / max(1, truth_tolerant.sum())
    ghost = 100.0 * fp / max(1, occ.sum())

    # --- 幽灵墙数字的正确读法(维护者 2026-10-04 补) ---
    # 下面这个"幽灵墙"用的是 0.3 格(0.015 m)严判。它**不是**"图里有这么多假墙":
    # 实测这张基准图的 342 个占据格到最近真墙表面的距离中位 0.008 m、p90 0.033 m、
    # **最大 0.034 m(0.69 格)** —— 也就是说没有一个占据格是站在空地上的。
    # 之所以还有"幽灵",是因为 3 cm 厚的墙落在 5 cm 栅格上必然被画胖一两格,
    # 那 130 格离真墙只有 1.5~3.4 cm。容差放到 0.8 格就归零。
    # 单独把距离分布打出来, 免得这个百分比被当成"图很脏"。
    _d = []
    _xs = origin[0] + np.arange(w) * res
    _ys = origin[1] + (h - 1 - np.arange(h)) * res
    _X, _Y = np.meshgrid(_xs, _ys)
    _best = np.full((h, w), 1e9)
    for (_n, _x, _y, _L, _T, _a) in segs:
        _ca, _sa = math.cos(_a), math.sin(_a)
        _dx, _dy = _X - _x, _Y - _y
        _u = _dx * _ca + _dy * _sa
        _v = -_dx * _sa + _dy * _ca
        _du = np.maximum(np.abs(_u) - _L / 2, 0.0)
        _dv = np.maximum(np.abs(_v) - _T / 2, 0.0)
        _best = np.minimum(_best, np.hypot(_du, _dv))
    _d = _best[occ]

    print("--- 1. 覆盖度 (决定能不能规划) ---")
    print("  unknown 比例      %5.1f%%   %s" % (pct_unk,
          "OK" if pct_unk < 15 else ("WARN" if pct_unk < 40 else "FAIL —— 有大片没建到")))
    print()
    print("--- 2. 墙体还原度 (决定会不会撞墙) ---")
    print("  严格实体墙覆盖    %5.1f%%   %s" % (cov,
          "OK" if cov > 70 else ("WARN" if cov > 40 else "FAIL —— 墙基本没进图")))
    print("  栅格容忍覆盖(+%.3fm) %5.1f%%" % (0.5 * res, tolerant_cov))
    print("  幽灵墙(空地标墙) %5.1f%%   %s" % (ghost,
          "OK" if ghost < 20 else ("WARN" if ghost < 50 else "FAIL —— 图里有大量假墙")))
    print("  (真实墙 %d 格 / 地图标占据 %d 格 / 其中幽灵 %d 格)"
          % (truth_strict.sum(), occ.sum(), fp))
    print()
    print("  >> 上面这个『幽灵 %%』是 %.3f m(%.1f 格)严判的结果, 别当成『图里有假墙』:" % (0.015, 0.3))
    print("     地图 %d 个占据格到最近真墙**表面**的距离:" % int(occ.sum()))
    print("        中位 %.3f m   p90 %.3f m   **最大 %.3f m (%.2f 格)**"
          % (np.percentile(_d, 50), np.percentile(_d, 90),
             _d.max(), _d.max() / res))
    for _tol in (0.025, 0.040, 0.050):
        _n = int((_d > _tol).sum())
        print("        容差 %.3f m (%.1f 格) -> 幽灵 %3d 格 (%.1f%%)"
              % (_tol, _tol / res, _n, 100.0 * _n / max(1, len(_d))))
    print("     3 cm 厚的墙落在 5 cm 栅格上必然被画胖一两格, 那不是假墙。")
    print("     判断『有没有假墙』看**最大距离**: 超过约 1 格才说明有占据格站在空地上。")
    print()
    # 逐墙
    print("  逐墙还原:")
    rows = []
    for wdef in segs:
        t1 = wall_mask([wdef], h, w, res, origin, cell_tolerance=False)
        rows.append((wdef[0], 100.0 * (t1 & occ).sum() / max(1, t1.sum())))
    for nm, r in sorted(rows, key=lambda x: x[1]):
        print("    %-8s %6.1f%%  %s" % (nm, r, "" if r > 70 else ("<== 基本缺失" if r < 40 else "<== 偏少")))
    print()
    print("--- 3. 航点连通性 (按车体 %.3fm) ---" % R_CIRC)
    print("  判据: 地图里标成占据的格子, 膨胀 %.3fm 后车走过去是否被挡。"
          % R_CIRC)
    print("  (只看地图自己的信息 —— 这才是导航时真正能拿到的信息)")
    # 车体按外接半径(原地转向需要 0.214m)会过于苛刻:
    # 北道净宽 0.47m, 扣 2x0.214 只剩 0.042m, 任何航点都会被判不可达,
    # 但车实际能过(内切半径 0.128m, 剩 0.214m)。所以这里用内切半径判"能不能过",
    # 外接半径只作为"能不能原地掉头"的备注。
    r_in = int(round(R_CIRC_IN / res))
    blocked = dilate(occ, r_in)
    free = ~blocked
    r = bfs_free(free, SPAWN, res, origin, 0.0)
    if r is None:
        print("  出生点被地图自己的障碍占死  FAIL  -> 这张图下根本发不了车")
    else:
        seen, _ = r
        allok = True
        for i, (x, y) in enumerate(ROUTE, 1):
            cx, cy = to_px(x, y, h, w, res, origin)
            ok = 0 <= cx < w and 0 <= cy < h and seen[cy, cx]
            allok &= ok
            print("    航点%d (%+.2f,%+.2f)  %s" % (i, x, y, "可达" if ok else "**不可达**"))
        print("  结论: %s" % ("按这张图能一路走到" if allok
                             else "按这张图走不到全部航点  FAIL"))
        if not allok:
            print("  说明: 航点不可达 = 局部代价地图会把这块判死,")
            print("        正是 DWA 活锁 / planner failed to produce path 的来源。")
    print()
    print("  附: 北道净宽 0.47m, 扣车体 %.3fm(内切)后剩 %.3fm —— 过得去但没余量,"
          % (R_CIRC_IN, 0.47 - 2 * R_CIRC_IN))
    print("      扣 %.3fm(外接, 原地转向所需)后剩 %.3fm —— 不足以原地转向,"
          % (R_CIRC, 0.47 - 2 * R_CIRC))
    print("      所以北道内不能调头, 航点朝向必须一路向前。")
    print()
    # 总评
    bad = 0
    if pct_unk >= 40:
        bad += 1
    if cov < 40:
        bad += 1
    if ghost >= 50:
        bad += 1
    verdict = "PASS 可以用于导航" if bad == 0 else \
        ("FAIL 不建议用于导航 (有 %d 项硬伤)" % bad if bad >= 2 else "WARN 勉强能用但有风险")
    print("=" * 68)
    print("总评: %s" % verdict)
    if bad:
        print()
        print("怎么修(按性价比排序):")
        if pct_unk >= 40:
            print("  1) 覆盖不够 -> 建图时把整条赛道都跑一遍:")
            print("     发车湾南下 -> 南道西行 -> 西走廊北上 -> 北道东行,")
            print("     再原地转两圈补全; 终点兜袋单独进一次。")
        if cov < 40:
            print("  2) 墙没进图 -> 别做\"擦幽灵墙\"这类修图, 或者擦之前先跑本工具对比;")
            print("     细长连续的线多半是真墙, 断续的才是幽灵。")
        if ghost >= 50:
            print("  3) 假墙太多 -> 同样的幽灵墙问题, 优先清掉它们。")
    print("=" * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
