# CONFIG_PROVENANCE.md —— 仓库里导航参数的来历(基线待考据)

维护者必须诚实标注基线来源。本文件记录仓库里 5 个 nav yaml + `amcl.launch`
的每一个取值**从哪来、能不能考证**。

## 结论先说

> **仓库中的导航参数是"基线待考据",不是经考证的"大会出厂默认值"。**
> 参赛者可自由调整;榜单会记录你提交版本的 SHA-256 前 16 位。

## 为什么不能直接说"这就是大会默认值"

1. **大会教程没有给数值。**《第一轮分站赛控制教程》"4、参数"一节只列了 5 个参数文件的
   **文件名**和它们各自的用途,然后说「为了更快更好的运动效果,**你需要调节其中的参数**」。
   PDF 里不存在任何具体数值。(可用 `pdftotext` 复核,见下方"复核命令")
2. **工作空间里现存的那份是被改过的。** 至少 `amcl.launch` 的 `update_min_d` 与
   `laser_max_beams` 明显是后续调过的值(见下表"被改过的痕迹"一列)。
3. 我们**没有**拿到大会原始包的独立副本:打榜容器把工作空间 bind mount 进去,
   镜像内没有第二份;容器里也不存在未挂载的原始工作空间。

## 我们采用的做法

采用**最早可考快照** `backups/control-opt-20260930-235940/`(2026-09-30,早于任何参赛
算法的改动)。它与当前工作空间的关键差异恰好落在"被调过的特征"上,方向自洽:

| 文件 | 参数 | 仓库基线(采用) | 后期被改成 | 判断依据 |
|---|---|---|---|---|
| `amcl.launch` | `update_min_d` | `0.10` | `0.05` | 09-30 快照为 0.10 |
| `amcl.launch` | `update_min_a` | `0.15` | `0.10` | 同上 |
| `amcl.launch` | `laser_max_beams` | `180` | `360` | 同上 |
| `amcl.launch` | `tf_broadcast` | 未设置(=true) | 未设置 | 两版都没有该参数 |
| `dwa_local_planner_params.yaml` | `xy_goal_tolerance` | `0.22` | `0.35` | 09-30 为 0.22;**无其它候选值佐证** |
| `costmap_common_params.yaml` | `inflation_radius` | `0.2` | `0.2` | **两版相同**,无改动痕迹 |
| `global_costmap_params.yaml` | plugins | `static_layer` + `inflation_layer` | 追加了 `obstacle_layer` | 09-30 只有两个 |
| `local_costmap_params.yaml` | `update_frequency` / `publish_frequency` | `10.0` / `10.0` | `8.0` / `3.0` | 09-30 为 10/10 |
| `move_base_params.yaml` | `controller_frequency` / `planner_frequency` | `15.0` / `5.0` | `10.0` / `2.0` | 09-30 为 15/5 |
| `dwa_local_planner_params.yaml` | `vx_samples` / `vth_samples` | `20` / `40` | `12` / `20` | 09-30 为 20/40 |
| `dwa_local_planner_params.yaml` | `latch_xy_goal_tolerance` | `false` | `false` | 两版相同 |
| `dwa_local_planner_params.yaml` | `min_vel_x` | `-0.10` | `-0.10` | **两版相同**,无改动痕迹 |

**诚实的不确定项**:`xy_goal_tolerance=0.22`、`inflation_radius=0.2`、`min_vel_x=-0.10`
这三项在 09-30 快照与后期版本里**取值相同**,因此我们**无法证明**它们是原厂值还是已经被改过。
若你从大会原始包里找到了不同的值,请提 PR 修正本文件并更新 SHA —— 这正是本文件存在的意义。

## 仓库基线的 SHA-256(前 16 位)

> 这些文件顶部都加了 `【基线待考据】` 注释头,`[待考据]` 项还有行内标注 ——
> 任何人打开文件都能立刻看到"这不是经考证的出厂默认值"。


| 文件 | SHA-256 前 16 位 |
|---|---|
| `workspace/src/ucar_navigation/config/costmap_common_params.yaml` | `275b3033efbd25bd` |
| `workspace/src/ucar_navigation/config/local_costmap_params.yaml` | `93a869a89f1b5619` |
| `workspace/src/ucar_navigation/config/global_costmap_params.yaml` | `e143fd4b8424179e` |
| `workspace/src/ucar_navigation/config/move_base_params.yaml` | `dd896e166f24de42` |
| `workspace/src/ucar_navigation/config/dwa_local_planner_params.yaml` | `8cfb10f19262c166` |
| `workspace/src/ucar_navigation/launch/amcl.launch` | `1517c4d41b849daa` |

复核命令:

```bash
cd workspace/src/ucar_navigation
for f in config/*.yaml launch/amcl.launch; do
  printf '%-45s %s\n' "$f" "$(sha256sum "$f" | cut -c1-16)"
done
```

## 红线组件的 SHA(禁改,用于核对)

| 文件 | SHA-256 前 16 位 |
|---|---|
| `env/benchmark_map.pgm` | `a9adb82b3796de3a` |
| `env/round1.world` | `2d9f7d5754a40bfc` |
| `workspace/src/car3/urdf/car3.urdf` | 见 `env/REDLINE_SHA.txt`(随仓库提供) |

## 基准图的来历与独立复核(2026-10-04)

`benchmark_map.pgm` 是在给定的 `round1.world` 里用 gmapping 实测建图,再按真几何校验
做过修图(幽灵墙清除 / 墙带减薄 / 空洞填白)。**它未改动任何几何。**

这一条是**载荷性**的:细则注 5 规定「使用非给定控制地图建图者,时间得分记 0 分,
到达终点区域的得分记 0 分」。所以基准图是否忠实于给定世界,决定了这个榜单上的
**每一行成绩**是否成立。

### 维护者独立复核(不采信任何一方的自报)

复核工具:本仓库的 `harness/check_map_quality.py`,加维护者另写的逐格距离统计。
下列数字都可由 `env/benchmark_map.pgm` 与 `env/round1.world` 自行重算。

| 项 | 维护者实测 | 结论 |
|---|---|---|
| `round1.world` 真值墙段数 | 9 | — |
| 地图标占据格数 | 342 | — |
| **每个占据格到最近真墙表面的距离** | 中位 0.008 m,p90 0.033 m,**最大 0.034 m(0.69 格)** | **幽灵占格 = 0**,没有一个占据格是假墙 |
| 逐墙法向偏移(p95) | −0.013 ~ +0.012 m | 9 面墙全部对齐,最大 13 mm(约 1/4 格) |
| 场地矩形内 unknown 格 | 0 | 场地已完整建到,无未建区 |
| 南墙 `Wall_0` | 长 4.000 m,内表面 y=−1.137 | 细则标 40 dm ✓ |
| 东墙 `Wall_2` | x=2.087,内表面 x=2.072 | — |
| 西墙 `Wall_22` | yaw −121.3° | 细则标 120° 斜角 ✓ |
| 岛西边 `Wall_18` | yaw 60° | ✓ |
| 岛距南墙 | 0.749 m(−1.137 → −0.388) | 细则标 7.5 dm ✓ |
| 起点框 `19th_start` | (1.70452, 0.264505) | 与地图/航点用的 (1.72, 0.27) 一致 ✓ |
| 白线 `white_line` | **两段**:(1.48651, 0.887172) 与 (1.55259, 0.850504) | 都在终点兜袋判定框 x∈[1.40,2.087] y∈[0.61,1.08] 内 ✓ |

结论:**几何忠实性成立,基准图符合细则「给定世界建图」的要求,不需要任何改动。**

### 一处没能复现的数字(不引用)

提交复核报告称「7 面墙 100% 覆盖、3 面墙 82~88%」。维护者用三种口径都算不出这个分布:

| 口径 | 结果 |
|---|---|
| 格重叠,容差 1 格(0.05 m) | 21.4% ~ 95.2%,2 面 ≥80% |
| 沿墙长每 2 cm 采样,法向容差 0.025 m | 42.1% ~ 100%,2 面 100%、4 面 ≥80% |
| 同上但掐掉端头各 5 cm | 31.9% ~ 100%,更低 |
| 同上但掐掉端头各 10 cm | 更低 |

**没有一种口径给出「7 面 100% + 3 面 82~88%」这个分布。** 覆盖率完全取决于口径,
而该报告未给出定义。这**不影响合规结论**(几何忠实性由上面那组距离数字独立支撑),
但这组百分比在补上定义之前不应被引用。

### `harness/check_map_quality.py` 报的数字要小心读

该工具报「幽灵墙 38.0% WARN」,容易被误读成「图里有 130 个假墙」。**不是。**
它用的是 **0.015 m(0.3 格)严判**:那 130 格离真墙只有 1.5~3.4 cm,是 5 cm 栅格下
墙画胖了一点,不是假墙 —— 容差放到 0.04 m(0.8 格)幽灵就归零。工具已补上距离分布输出。

### 为什么仍然要保持警惕

即便几何忠实,**在地图上算出来的走廊宽度和世界里的真实宽度仍可能差几厘米**,
因为 3 cm 厚的墙在 5 cm 栅格上必然被量化。北道净宽只有 0.48 m、车宽 0.256 m ——
几厘米就是生死之差。凡是"按地图算几何可行性"的结论,都要回到真几何复核一遍。

## 复核命令(如何验证本文件)

```bash
# 1. 教程确实没给数值
pdftotext -layout "ROS第一轮下发/第一轮下发/教程/第⼀轮分站赛控制教程.pdf" - \
  | grep -nE "inflation|xy_goal|laser_max_beams|update_min_d" || echo "教程未出现任何数值(符合预期)"

# 2. 基准图与真几何整体零偏移
python3 harness/check_map_quality.py     # 需要 numpy + pillow
```