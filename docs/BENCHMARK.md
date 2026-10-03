# BENCHMARK.md —— 跑分操作手册

三条命令。全程在**宿主机**执行(脚本内部会 `docker exec` 进容器)。

---

## 0. 命名与目录约定

- 每轮一个 **TAG**(你自己起,建议 `<模型>-<组别>-<序号>`,如 `sb-A0-1`)。
- 产物全部落在仓库的 `runs/`,可直接作为提交证据:

```
runs/
├── <TAG>/trace.csv            5Hz 采样: t_sim,x,y,yaw,cone_dist,nearest_cone,in_pocket
├── sim_run_<TAG>.log          总控: 起停仿真/等各节点就绪/点发车/完赛判定/墙钟与仿真耗时
├── commander_<TAG>.log        你的 commander 的 stdout(含分段用时与统计行)
└── sim_nodes_<TAG>.log        导航栈 stderr
```

---

## 1. 无锥轮(A0 组)

```bash
bash harness/bench_run.sh <TAG> 2400
```

例:`bash harness/bench_run.sh sb-A0-1 2400`

这一轮用基准图、不摆锥桶,对应细则的"不带锥桶组"。

---

## 2. 带锥轮(B 组)

### 2.1 先留证:干跑生成摆放

```bash
python3 harness/spawn_cones.py --dry-run --seed <S>
```

它会打印每个锥桶的坐标、所在航段、两侧通道宽度与通过空间,并给出复现用的完整命令。
**把这段输出原样贴进你的提交**(PR 描述或 `runs/<TAG>/cones.txt`)。

### 2.2 再开跑

```bash
bash harness/bench_run.sh <TAG> 2400 "<x1,y1;x2,y2;x3,y3" <S>
```

例(标准配置 B2 = seed 7):

```bash
bash harness/bench_run.sh sb-B2-1 2400 "1.419,-0.609;-0.653,-0.446;-0.422,0.892" 7
```

> 第四个参数 `seed` 传下去后,`spawn_cones.py` 会**在仿真里真的插锥桶**;
> 第三个参数则用于把同一份数据同时交给 `bench_monitor`(计分口径)和
> `/ucar_commander/cones`(让你的算法知道锥桶在哪)。两者必须一致。

### 2.3 标准配置(与他人可比)

| 轮次 | seed | 锥桶坐标 |
|---|---|---|
| **B1** | `42` | `1.399,-0.680; -0.632,-0.724; -0.146,0.269` |
| **B2** | `7` | `1.419,-0.609; -0.653,-0.446; -0.422,0.892` |

复核(应当逐位复现上表):

```bash
python3 harness/spawn_cones.py --dry-run --seed 42
python3 harness/spawn_cones.py --dry-run --seed 7
```

> **只能用标准 seed 跟别人比。** 细则要求「比赛时每队障碍物摆放位置一样」。
> 若你用别的种子(比如 `--seed 11`),榜单会把该行标为"自选配置",
> 时间分**不与标准组混排**。

---

## 3. 计分

```bash
python3 harness/bench_score.py <TAG>
```

输出单行 JSON,字段含义:

| 字段 | 含义 |
|---|---|
| `finished` | 是否完赛(commander 日志里出现「完赛!」) |
| `sim_time` | **仿真秒**总用时 ← 这是计分用的时间 |
| `wall_time` | 墙钟秒,仅供调试 |
| `depart` | 车心**第一次离开起点区域**的仿真时刻;非 null 即「成功发车」5 分 |
| `pocket_stop` | 车心**末位置**是否在终点兜袋内 → 「到达终点区域」10 分 |
| `reach_final` | 与 `pocket_stop` 同义(True / null),保留字段 |
| `final_xy` | 末位置坐标 `[x, y]`,自查用 |
| `collisions` | 碰撞事件数(代理口径,连续接触已合并为一次) |
| `wp_time` | 逐航点用时(秒),长度 = 到达的航点数 |
| `stats` | 从 commander 日志抓的计数 `{reloc, clear, toggles, retries, stalled}` |
| `score` | `{depart, final, cones_map, collision, line}`,取值 5 / 10 / 5 / ≤0 / ≤0 |
| `subtotal` | **导航小计** = 上面五项之和(细则口径) |
| `notes` | 人工提示,例如「未停进兜袋: 选图 5 分不计」 |

### 计分实现要点(照抄 `harness/bench_score.py`,口径不可改)

```
subtotal = depart(0|5) + pocket_stop(0|10) + cones_map(0|5)
         + collision(-min(2*碰撞数, 5)) + line(0|-2)
```

三个容易被误解的地方:

- **`line`**:脚本只在「完赛但末位置不在兜袋」时按 **一轮白线外** 估 `-2`。
  细则里的 -5 / -8 / -10 是现场裁判数轮子判的,自动计分拿不到那个信息,
  只能取最轻的一档;`notes` 会写明这是估算。
- **`cones_map`(选带锥桶地图 5 分)**:带了锥桶才可能拿,而且**没停进兜袋就不给** ——
  这条链是「选带锥桶图 → 跑完 → 停进去」。
- **`final` 10 分也依赖 `pocket_stop`**,不是「中途路过兜袋就算」。

时间分由榜单按组内排名赋([RULES.md](RULES.md) 第 3 节),不在这儿算。

---

## 4. 口径说明(必须知道,否则会误判自己的成绩)

### 4.1 计时用仿真秒,和你的机器无关

一切以 `/clock` 为准。软渲染 RTF≈0.1~0.3、GPU RTF≈1.0,出的成绩可直接比较。
**别拿墙钟时间去和别人比。**日志里 `耗时: 墙钟 Xs / 仿真 Ys` 两个都有,计分用 `Y`。

### 4.2 碰撞是代理估算,不是裁判目判

口径:**车中心与锥桶中心距离 < 0.30 m 记一次事件**,连续接触去重
(离开 0.30 m 半径后再接触才算新事件)。每罚 2 分,上限 5 分。
**碰墙不扣分**(细则注 3)。

代理口径与裁判目判可能有偏差,维护者复跑时会核对量级(见 [SUBMISSION.md](SUBMISSION.md))。

### 4.3 "三次尝试机会"由你的 commander 自己用

细则给了每队三次发车机会;本榜单把**一轮视为一次尝试**。
一轮之内你可以任意重试 / 换偏置 / 跳过航点 —— 这属于算法内部行为,不加罚。
但**一轮只能发一次车**,不能靠"中途再发一次车"刷时间。

### 4.4 航点表必须两处一致

参赛者的 `commander.py` 与 `harness/spawn_cones.py` 的 `ROUTE` 必须逐位相同,
理由见 [RULES.md](RULES.md) 第 4 节。榜单会检查。

---

## 5. 常见跑法问题

| 现象 | 说明 |
|---|---|
| `finished=false` 且车没动 | 仓库默认是**占位桩 commander**,它不导航。见 DEPLOY.md 第 5 节。 |
| `finished=false` 但有碰撞 | 正常:中途 DNF 也可能蹭到锥桶。 |
| `finished=true` 但 `reach_final=false` | 你的日志打了「完赛!」但末位置不在兜袋。计分仍按兜袋判,自查 `in_pocket`。 |
| 跑很久不出 `trace.csv` | 监视节点是后台起的,首次写盘在第一轮采样后;或 `/clock` 没起来,看 `sim_nodes_<TAG>.log`。 |
| 容器里手动重跑 | `docker exec -it smartcar-bench bash` 然后 `bash harness/run_sim.sh 2400`。 |
| 换地图做 A/B | `MAP=/abs/path/map.pgm bash harness/bench_run.sh <TAG> 2400`。**注意:用非给定地图则到达终点与时间分记 0**(细则注 5)。 |