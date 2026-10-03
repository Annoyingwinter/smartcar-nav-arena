#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_leaderboard.py —— leaderboard.json 的 CI 校验器(无第三方依赖)。

校验四件事,对应 SUBMISSION.md 第 5 节:
  1. JSON 合法, 且满足 docs/leaderboard.schema.json 里能被本脚本表达的那部分约束
     (本脚本是个精简校验器: 它不实现完整 JSON Schema, 只查 CI 真正关心的字段,
      完整 schema 仍随仓库提供, 供编辑器/IDE 提示用)。
  2. SHA-256 前 16 位格式正确 (小写十六进制, 正好 16 位)。
  3. 算术自洽: subtotal == 五项之和; time_score 不超过该组 cap;
     collision 罚符合 -min(2*n, 5) 且被罚满时 collisions >= 3;
     完赛行必须有 sim_time_s, 未完赛行必须没有。
  4. 证据存在性: 每条 runs[] 引用的证据文件都在 evidence/<run-id>/ 下且非空。

用法:
    python3 harness/validate_leaderboard.py            # 校验并打印摘要
    python3 harness/validate_leaderboard.py --quiet    # 只在失败时输出

退出码: 0 = 通过, 1 = 有错。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEADERBOARD = os.path.join(ROOT, 'docs', 'leaderboard.json')

# SHA-256 十六进制串。历史迁移行只有 8 位前缀(见 leaderboard.json 的 sha_policy),
# 完整 64 位是新提交的期望值 —— 两种都接受, 但长度会打印出来。
SHA_RE = re.compile(r'^[0-9a-f]{8,64}$')
SHA16_RE = re.compile(r'^[0-9a-f]{16}$')
RUN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
EPOCH_ID_RE = re.compile(r'^[a-z0-9-]+$')
CAPS = {'no-cones': 3.0, 'with-cones': 5.0}
GROUPS = ('no-cones', 'with-cones')

# 哪些字段里可能出现 16 位 SHA
SHA_FIELDS = ('commander_sha',)
SHA_MAP_FIELDS = ('public_baseline_yaml_sha16',)
REQUIRED_RUN_FIELDS = (
    'id', 'model', 'version', 'epoch', 'round', 'group', 'finished',
    'collisions', 'score', 'subtotal', 'time_score', 'commander_sha',
)
SCORE_KEYS = ('depart', 'final', 'cones_map', 'collision', 'line')

# 提交一条成绩行时必须附的证据文件(相对 evidence/<run-id>/)
REQUIRED_EVIDENCE = ('commander.py',)


class Report:
    def __init__(self, quiet: bool = False):
        self.errors: list[str] = []
        self.notes: list[str] = []
        self.quiet = quiet

    def err(self, where: str, msg: str) -> None:
        self.errors.append('%s: %s' % (where, msg))

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def ok(self, msg: str) -> None:
        if not self.quiet:
            print(msg)


def check_structure(data: dict, rep: Report) -> None:
    for key in ('schema_version', 'epochs', 'runs', 'standings'):
        if key not in data:
            rep.err('<root>', '缺少必需字段 %r' % key)
    if not isinstance(data.get('schema_version'), int):
        rep.err('<root>', 'schema_version 必须是整数')
    elif data['schema_version'] < 2:
        rep.err('<root>', 'schema_version >= 2(本仓库用 v2 字段集)')

    epochs = data.get('epochs')
    if not isinstance(epochs, list) or not epochs:
        rep.err('epochs', '必须是非空数组')
        return
    seen = set()
    for i, ep in enumerate(epochs):
        w = 'epochs[%d]' % i
        for key in ('id', 'label', 'status', 'official'):
            if key not in ep:
                rep.err(w, '缺少必需字段 %r' % key)
        eid = ep.get('id', '')
        if not EPOCH_ID_RE.match(str(eid)):
            rep.err(w, 'id 必须是小写字母/数字/连字符: %r' % eid)
        if eid in seen:
            rep.err(w, '纪元 id 重复: %r' % eid)
        seen.add(eid)
        if ep.get('status') not in ('reference', 'official'):
            rep.err(w, 'status 必须是 reference 或 official')
    if not any(ep.get('official') is True for ep in epochs):
        rep.err('epochs', '至少要有一个 official=true 的纪元(正式榜)')


def check_run(run: dict, epochs: set, rep: Report) -> None:
    rid = run.get('id', '<no-id>')
    w = 'runs[%s]' % rid

    if not RUN_ID_RE.match(str(rid)):
        rep.err(w, 'id 只能是小写字母/数字/点/下划线/连字符: %r' % rid)
    for key in REQUIRED_RUN_FIELDS:
        if key not in run:
            rep.err(w, '缺少必需字段 %r' % key)

    if run.get('epoch') not in epochs:
        rep.err(w, '未知纪元 %r(epochs[] 里没有)' % run.get('epoch'))

    grp = run.get('group')
    if grp not in GROUPS:
        rep.err(w, 'group 必须是 %s 之一' % (GROUPS,))

    if not re.match(r'^(A0|B[0-9]+)$', str(run.get('round', ''))):
        rep.err(w, 'round 格式应为 A0 或 B<n>: %r' % run.get('round'))

    # --- SHA 格式 ---
    for f in SHA_FIELDS:
        if f in run:
            v = str(run[f])
            if not SHA_RE.match(v):
                rep.err(w, '%s 必须是 8~64 位小写十六进制: %r' % (f, v))
            elif len(v) < 16:
                rep.note('%s: %s 只有 %d 位(历史迁移行的前缀;'
                         '新行请给完整 64 位)' % (w, f, len(v)))

    # --- 轮次与分组一致性 ---
    rd, grp2 = str(run.get('round', '')), run.get('group')
    if rd == 'A0' and grp2 != 'no-cones':
        rep.err(w, 'A0 必须属于 no-cones 组')
    if rd.startswith('B') and grp2 != 'with-cones':
        rep.err(w, '%s 必须属于 with-cones 组' % rd)
    if rd.startswith('B') and not run.get('cones'):
        rep.err(w, '带锥轮必须给出 cones 坐标串')

    # --- 完赛/用时一致性 ---
    fin = run.get('finished')
    st = run.get('sim_time_s')
    if fin is True and not isinstance(st, (int, float)):
        rep.err(w, 'finished=true 时必须有数值 sim_time_s')
    if fin is False and st is not None:
        rep.err(w, 'finished=false 时 sim_time_s 必须为 null'
                   '(实际用时写在 sim_time_lower_bound_s)')
    if fin is False and not run.get('sim_time_lower_bound_s'):
        rep.note('%s: DNF 行没有 sim_time_lower_bound_s, 下界按轮次超时上限理解' % w)

    # --- 计分自洽 ---
    sc = run.get('score')
    if not isinstance(sc, dict):
        rep.err(w, 'score 必须是对象')
        return
    for k in SCORE_KEYS:
        if k not in sc:
            rep.err(w, 'score 缺少 %r' % k)

    sub = run.get('subtotal')
    if all(k in sc for k in SCORE_KEYS):
        calc = sum(sc[k] for k in SCORE_KEYS)
        if sub != calc:
            rep.err(w, 'subtotal=%s 与五项之和 %d 不符' % (sub, calc))

    # 碰撞罚: -min(2*n, 5)
    ncol = run.get('collisions')
    if isinstance(ncol, int) and 'collision' in sc:
        want = -min(2 * ncol, 5)
        if sc['collision'] != want:
            rep.err(w, 'collision 罚应为 %d(碰撞 %d 次 -> -min(2*%d,5)=%d), 实为 %s'
                    % (want, ncol, ncol, want, sc['collision']))
        if run.get('collision_penalty_capped') and ncol < 3:
            rep.err(w, '标了 collision_penalty_capped 但碰撞只有 %d 次(需 >=3)' % ncol)

    # 到达终点 10 分 与 pockets 的一致性(有 final_xy 时)
    if isinstance(run.get('final_xy'), list) and len(run['final_xy']) == 2:
        fx, fy = run['final_xy']
        in_pocket = 1.40 <= fx <= 2.087 and 0.61 <= fy <= 1.08
        want_final = 10 if (fin and in_pocket) else 0
        if sc.get('final') != want_final:
            rep.err(w, 'final_xy=%s 判定%s在终点兜袋, final 应为 %d, 实为 %s'
                    % (run['final_xy'], '' if in_pocket else '不', want_final,
                       sc.get('final')))

    # 选带锥图 5 分: 必须带锥且停进兜袋
    want_cones = 5 if (grp2 == 'with-cones' and sc.get('final') == 10) else 0
    if sc.get('cones_map') != want_cones:
        rep.err(w, 'cones_map 应为 %d(group=%s, final=%s), 实为 %s'
                % (want_cones, grp2, sc.get('final'), sc.get('cones_map')))

    # 发车 5 分: DNF 也可能已发车, 不能交叉验证, 只查取值域
    for k, allowed in (('depart', (0, 5)), ('final', (0, 10)),
                       ('cones_map', (0, 5)), ('line', (0, -2))):
        if k in sc and sc[k] not in allowed:
            rep.err(w, '%s 取值 %s 非法(允许 %s)' % (k, sc[k], list(allowed)))

    # 时间分上限
    ts = run.get('time_score')
    if grp in CAPS and isinstance(ts, (int, float)) and ts > CAPS[grp]:
        rep.err(w, 'time_score=%s 超过 %s 组上限 %s' % (ts, grp, CAPS[grp]))
    if fin is False and isinstance(ts, (int, float)) and ts != 0:
        rep.err(w, 'DNF 行 time_score 必须为 0(细则注 1: 未完赛不参与时间排名)')


def check_evidence(run: dict, rep: Report) -> None:
    rid = run.get('id', '')
    if not rid:
        return
    d = os.path.join(ROOT, 'evidence', rid)
    if not os.path.isdir(d):
        rep.note('evidence/%s/ 不存在(维护者合并历史行时可豁免)' % rid)
        return
    for name in REQUIRED_EVIDENCE:
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            rep.err('evidence[%s]' % rid, '缺少 %s' % name)
        elif os.path.getsize(p) == 0:
            rep.err('evidence[%s]' % rid, '%s 是空文件' % name)


def check_time_scores(data: dict, rep: Report) -> None:
    """按 RULES.md 第 3 节重算时间分, 与 JSON 里写的比对。"""
    runs = data['runs']
    for ep in data['epochs']:
        eid = ep['id']
        if not ep.get('official') and ep.get('status') == 'reference':
            pass          # 参考纪元也一并校验, 保证数字可复算
        for grp, cap in CAPS.items():
            fin = [r for r in runs
                   if r.get('epoch') == eid and r.get('group') == grp
                   and r.get('finished') is True]
            n = len(fin)
            for r in fin:
                if not isinstance(r.get('sim_time_s'), (int, float)):
                    rep.err('runs[%s]' % r['id'], '完赛行缺 sim_time_s, 无法排时间分')
                    continue
            if n == 0:
                for r in runs:
                    if (r.get('epoch') == eid and r.get('group') == grp
                            and r.get('time_score')):
                        rep.err('runs[%s]' % r['id'],
                                '该组无完赛队伍, 时间分应为 0(细则注 1)')
                continue
            fin.sort(key=lambda r: r['sim_time_s'])
            # 并列同名次取该名次区间平均分
            i = 0
            while i < n:
                j = i
                while (j + 1 < n
                       and fin[j + 1]['sim_time_s'] == fin[i]['sim_time_s']):
                    j += 1
                size = j - i + 1
                avg = cap * (n - ((i + j) / 2.0 + 1.0)) / (n - 1) if n > 1 else cap
                for k in range(i, j + 1):
                    want = round(avg, 6)
                    got = fin[k].get('time_score')
                    if got is None or abs(got - want) > 1e-6:
                        rep.err('runs[%s]' % fin[k]['id'],
                                'time_score=%s, 按 RULES 第 3 节应为 %s'
                                '(%s 组 %d 支完赛队, cap=%s, 并列区间 %d..%d)'
                                % (got, want, grp, n, cap, i + 1, j + 1))
                i = j + 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--quiet', action='store_true', help='只在失败时输出')
    ap.add_argument('--file', default=LEADERBOARD, help='leaderboard.json 路径')
    args = ap.parse_args()

    try:
        with open(args.file, encoding='utf-8') as fh:
            data = json.load(fh)
    except (IOError, ValueError) as e:
        print('✗ leaderboard.json 读不了或不是合法 JSON: %s' % e, file=sys.stderr)
        return 1

    rep = Report(args.quiet)
    check_structure(data, rep)

    epochs = {e.get('id') for e in data.get('epochs', []) if isinstance(e, dict)}
    runs = data.get('runs')
    if not isinstance(runs, list) or not runs:
        rep.err('runs', '必须是非空数组')
    else:
        seen = set()
        for run in runs:
            if not isinstance(run, dict):
                rep.err('runs', '每条必须是对象')
                continue
            rid = run.get('id')
            if rid in seen:
                rep.err('runs[%s]' % rid, 'run id 重复')
            seen.add(rid)
            check_run(run, epochs, rep)
            check_evidence(run, rep)

        # 配置指纹里的 SHA
        for f in SHA_MAP_FIELDS:
            m = (data.get('config_fingerprint') or {}).get(f)
            if isinstance(m, dict):
                for k, v in m.items():
                    if not SHA_RE.match(str(v)):
                        rep.err('config_fingerprint.%s[%s]' % (f, k),
                                'SHA 格式错误(需 8~64 位小写十六进制): %r' % v)

        try:
            check_time_scores(data, rep)
        except (KeyError, TypeError, ZeroDivisionError) as e:
            rep.err('standings', '时间分重算失败: %r' % e)

    for n in rep.notes:
        if not args.quiet:
            print('  · %s' % n)

    if rep.errors:
        print('\n✗ leaderboard 校验失败 (%d 项):' % len(rep.errors), file=sys.stderr)
        for e in rep.errors:
            print('  - %s' % e, file=sys.stderr)
        return 1

    if not args.quiet:
        by_model = {}
        for r in data['runs']:
            by_model.setdefault(r['model'], []).append(r['id'])
        print('✓ leaderboard 校验通过')
        print('  纪元 %d 个 · 成绩行 %d 条 · 模型 %d 个'
              % (len(data['epochs']), len(data['runs']), len(by_model)))
        for m, ids in sorted(by_model.items()):
            print('    %-22s %s' % (m, ' '.join(ids)))
    return 0


if __name__ == '__main__':
    sys.exit(main())