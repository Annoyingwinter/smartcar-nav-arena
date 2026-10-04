#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_map_gaps.py —— 把 benchmark_map.pgm 画出来, 标出"膨胀后仍看不见"的墙段。

维护者内部诊断脚本。输出 /tmp/opencode/map_gaps.png 与一张逐段报表。
判据: 沿每面墙中线每 1cm 采样, 问该点在"地图占据格按 inflation_radius 膨胀后"
是否仍为空; 连续空段 >= 5cm 即记为一个洞。
"""
import math
import os
import importlib.util

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location('cmq', os.path.join(HERE, '..', 'harness', 'check_map_quality.py'))
cmq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmq)

RES, ORIGIN = 0.05, (-5.0, -5.0)
SEGS = cmq.walls()
ROUTE = [(1.72, 0.27), (1.72, -0.75), (0.20, -0.76), (-0.75, -0.25),
         (-0.35, 0.45), (-0.15, 0.70), (0.50, 0.84), (1.55, 0.87), (1.80, 0.85)]


def dilate(mask, r):
    out = mask.copy()
    n = int(math.ceil(r / RES))
    for dy in range(-n, n + 1):
        for dx in range(-n, n + 1):
            if dx * dx + dy * dy > (r / RES) ** 2:
                continue
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def dist_to_route(x, y):
    best = 1e9
    for i in range(len(ROUTE) - 1):
        ax, ay = ROUTE[i]
        bx, by = ROUTE[i + 1]
        vx, vy = bx - ax, by - ay
        l2 = vx * vx + vy * vy
        t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / l2))
        best = min(best, math.hypot(x - (ax + t * vx), y - (ay + t * vy)))
    return best


def main():
    im = np.array(Image.open(os.path.join(HERE, '..', 'env', 'benchmark_map.pgm')))
    occ = im < 64
    h, w = occ.shape
    inf = dilate(occ, 0.20)

    # 逐墙找洞
    gaps = {}
    for name, x, y, L, T, a in SEGS:
        ca, sa = math.cos(a), math.sin(a)
        n = int(L / 0.01)
        flags = []
        for i in range(n + 1):
            u = -L / 2 + L * i / n
            px, py = x + u * ca, y + u * sa
            c = int(math.floor(round((px - ORIGIN[0]) / RES, 9)))
            r = h - 1 - int(math.floor(round((py - ORIGIN[1]) / RES, 9)))
            flags.append(not (0 <= r < h and 0 <= c < w and inf[r, c]))
        segs = []
        i = 0
        while i < n:
            if flags[i]:
                j = i
                while j < n and flags[j]:
                    j += 1
                if (j - i) * 0.01 >= 0.05:
                    segs.append((i * 0.01 - L / 2, j * 0.01 - L / 2))
                i = j
            else:
                i += 1
        gaps[name] = segs

    S = 10
    g = np.full(im.shape, 255, np.uint8)
    g[im == 205] = 226
    g[im < 64] = 0
    img = Image.fromarray(g, 'L').convert('RGB').resize((192 * S, 192 * S), Image.NEAREST)
    dr = ImageDraw.Draw(img)

    def P(px, py):
        return ((px - ORIGIN[0]) / RES * S, (191 - (py - ORIGIN[1]) / RES) * S)

    dr.line([P(p[0], p[1]) for p in ROUTE], fill=(0, 150, 0), width=3)
    for p in ROUTE[1:]:
        cx, cy = P(p[0], p[1])
        dr.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=(0, 90, 0), width=3)

    report = []
    for name, x, y, L, T, a in SEGS:
        ca, sa = math.cos(a), math.sin(a)
        corners = [(x + u * ca - v * sa, y + u * sa + v * ca)
                   for (u, v) in ((-L / 2, -T / 2), (L / 2, -T / 2),
                                  (L / 2, T / 2), (-L / 2, T / 2))]
        dr.polygon([P(c[0], c[1]) for c in corners], outline=(220, 0, 0))
        cx, cy = P(x, y)
        dr.text((cx - 20, cy - 24), name, fill=(200, 0, 0))
        for (u0, u1) in gaps[name]:
            dr.line([P(x + u0 * ca, y + u0 * sa), P(x + u1 * ca, y + u1 * sa)],
                    fill=(255, 140, 0), width=10)
            mx, my = x + (u0 + u1) / 2 * ca, y + (u0 + u1) / 2 * sa
            tm = P(mx, my)
            dr.text((tm[0] - 52, tm[1] + 10), '%s hole %.2fm' % (name, u1 - u0),
                    fill=(190, 80, 0))
            report.append((name, u1 - u0, mx, my, dist_to_route(mx, my)))

    x0, y0 = P(-2.05, 1.34)
    x1, y1 = P(2.30, -1.40)
    img = img.crop((int(x0), int(y0), int(x1), int(y1)))

    leg = Image.new('RGB', (img.width, 72), (255, 255, 255))
    dl = ImageDraw.Draw(leg)
    dl.text((10, 5), 'benchmark_map.pgm  SHA a9adb82b    black = map occupied'
                     '    grey = unknown    white = free', fill=(0, 0, 0))
    dl.rectangle([10, 30, 40, 46], outline=(220, 0, 0))
    dl.text((48, 32), 'round1.world true wall (outline only, NOT filled)', fill=(0, 0, 0))
    dl.rectangle([430, 30, 460, 46], fill=(255, 140, 0))
    dl.text((468, 32), 'hole: planner cannot see it even after 0.20m inflation', fill=(0, 0, 0))
    dl.line([880, 38, 910, 38], fill=(0, 150, 0), width=3)
    dl.text((918, 32), '8-waypoint route', fill=(0, 0, 0))

    out = Image.new('RGB', (img.width, img.height + 72), (255, 255, 255))
    out.paste(img, (0, 72))
    out.paste(leg, (0, 0))
    out.save(os.path.join(HERE, 'map_gaps.png'))

    print('%-9s %-8s %-18s %s' % ('wall', 'hole', 'midpoint', 'dist-to-route'))
    for name, ln, mx, my, dd in sorted(report, key=lambda t: -t[4]):
        tag = '  <== off route, irrelevant' if dd > 0.6 else ''
        print('%-9s %.2f m  (%+.2f,%+.2f)   %.2f m%s' % (name, ln, mx, my, dd, tag))
    print('\nimage: %s  (%dx%d)' % ((os.path.join(HERE, 'map_gaps.png'),) + out.size))


if __name__ == '__main__':
    main()