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
| `workspace/src/ucar_navigation/launch/amcl.launch` | `e22539fdf7390945` |

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

## 基准图的来历(为什么它和真几何差几厘米)

`benchmark_map.pgm` 是**人工修过的图**:用户先实测建图,再按真几何(`round1.world`)校验,
做过"幽灵墙清除 / 墙带减薄 / 空洞填白"。所以它和真墙**不是逐格一致**的 ——
离线比对(`harness/check_map_quality.py`)给出的是"最优平移 = (0,0),真墙覆盖率 100%",
即**整体零偏移**,但局部墙带有厘米级差异。

这一点很重要:在地图上算出来的走廊宽度,和世界里的真实宽度可能差几厘米,
而北道净宽只有 0.48m、车宽 0.256m —— 几厘米就是生死之差。
凡是"按地图算几何可行性"的结论,都要回到真几何复核一遍。

## 复核命令(如何验证本文件)

```bash
# 1. 教程确实没给数值
pdftotext -layout "ROS第一轮下发/第一轮下发/教程/第⼀轮分站赛控制教程.pdf" - \
  | grep -nE "inflation|xy_goal|laser_max_beams|update_min_d" || echo "教程未出现任何数值(符合预期)"

# 2. 基准图与真几何整体零偏移
python3 harness/check_map_quality.py     # 需要 numpy + pillow
```