# SUBMISSION.md —— 提交、审核、上榜流程

一句话:**提一个 PR,改一个 JSON,附上能被别人复现的证据。** 维护者复跑验证后才合。

---

## 1. 提交物(PR 必须包含)

### 1.1 必改

**`docs/leaderboard.json`** —— 往 `runs[]` 数组里追加一条(或多条)记录。
**不要**手改 `standings.*`,那是算出来的;维护者合并时会用
`harness/` 里的计算脚本重算(见第 4 节)。

### 1.2 必附证据

| 证据 | 放在 | 说明 |
|---|---|---|
| commander 全源码 | `evidence/<run-id>/commander.py` | 你提交的那一版,**原样**,不要删注释(注释里的实测数据是别人最需要的部分) |
| 自建辅助文件 | `evidence/<run-id>/` | 与 commander 同目录的其它 `.py` |
| 改过的 nav yaml | `evidence/<run-id>/config/` | 只放你改动的那些 |
| 跑分日志 | `evidence/<run-id>/commander_<TAG>.log`、`sim_run_<TAG>.log` | 总控日志里必须能看到「耗时: 墙钟 X s / 仿真 Y s」 |
| 轨迹 | `evidence/<run-id>/trace.csv` | `bench_monitor` 的 5Hz 采样,原样 |
| 摆锥干跑输出 | 贴在 PR 描述里,或存 `evidence/<run-id>/cones.txt` | `python3 harness/spawn_cones.py --dry-run --seed <S>` 的完整输出 |
| 复现命令 | PR 描述 | 见下面模板 |

> 仓库的 `runs/` 目录默认在 `.gitignore` 里,证据请放 `evidence/`。

### 1.3 PR 描述模板

```markdown
## 提交成绩: <模型名> <版本>

| 字段 | 值 |
|---|---|
| 模型名 / 版本 | GLM-5.3 / v1 |
| run id | glm-v1-a0 |
| 纪元 | public-baseline |
| 轮次 | A0(无锥组) / B1(seed 42) / B2(seed 7) |
| commander SHA-256(完整 64 位) | `sha256sum .../commander.py` 的整串 |
| nav yaml SHA-256(各 16 位即可) | costmap_common=c399f462074dc95d, local=..., global=..., move_base=..., dwa=..., amcl.launch=... |
| 仿真用时 | 67.6 s |
| 完赛 | 是 |
| 碰撞(代理) | 0 |
| bench_score JSON | (整段贴上) |

### 复现命令
```bash
bash harness/build_workspace.sh
bash harness/bench_run.sh <TAG> 2400
python3 harness/bench_score.py <TAG>
# 带锥轮追加:
python3 harness/spawn_cones.py --dry-run --seed 7
bash harness/bench_run.sh <TAG> 2400 "1.419,-0.609;-0.653,-0.446;-0.422,0.892" 7
```

### 算法说明(必填,至少 3 行)
说清你的决策结构、卡死怎么判、卡住了怎么办。
**不要**贴别人的代码或从别人代码里抄的段落。

### 我改动的文件清单
- workspace/src/ucar_commander/scripts/commander.py
- workspace/src/ucar_navigation/config/dwa_local_planner_params.yaml
（红线文件一个都不许动,自查 `bash harness/verify_redline.sh`）
```

---

## 2. 证据的最低标准

维护者只接受**可复现**的证据。三条硬要求:

1. **commander 源码必须完整,且 SHA 给足。** 只给 SHA 不给源码的 PR 直接打回 ——
   审稿人无法判断这份 SHA 是不是你真正跑分时的那份。
   SHA 一律给 `sha256sum` 的**完整 64 位**:前缀便于肉眼比对,完整串才能当指纹用。
   > 榜单里已有的 8 条历史行只有 **8 位**前缀 —— 那是前代榜单的遗留。维护者**没有**去猜
   > 后面 8 位:补全一个自己没见过的 SHA 就是伪造。理由写在 `leaderboard.json` 的 `sha_policy`。
   > **你的新行请给完整 64 位。**
2. **`trace.csv` 必须存在且非空。** 它是碰撞口径的唯一数据来源;没有它,
   `collisions` 字段无法核对。
3. **`sim_run_<TAG>.log` 里必须有仿真耗时。** 墙钟不算数(见
   [BENCHMARK.md](BENCHMARK.md) 第 4.1 节)。

自检:

```bash
bash harness/verify_redline.sh            # 红线组件未被改动
sha256sum workspace/src/ucar_commander/scripts/commander.py
                                                  # 整串必须与 PR 里写的一致
wc -l runs/<TAG>/trace.csv                  # 必须 > 0
grep "耗时: 墙钟" runs/sim_run_<TAG>.log     # 必须有
```

---

## 3. 维护者的复跑义务

维护者收到 PR 后**必须**做同配置复跑,不能只看 JSON:

| 偏差 | 处理 |
|---|---|
| 完赛/未完赛一致,用时偏差 ≤ 10% | 通过 |
| 完赛/未完赛一致,用时偏差 > 10% | **打回**,在 PR 里留记录(实测用时、偏差、可能原因) |
| 完赛状态不一致 | **打回**。这是最严重的一种:说明证据与成绩不匹配 |
| 碰撞数差 ≥ 3 次 | 要求说明;仍对不上则打回 |
| SHA 对不上 / 源码缺失 / 红线被改 | **直接打回**,不进入复跑 |

复跑结果与提交值的对比**必须贴在 PR 里**(哪怕只贴一行),这是审核留痕的一部分。

> 为什么允许 10%:仿真是确定性的,但 Gazebo 物理 + AMCL 粒子滤波存在少量非确定性
> (粒子采样、时钟步进)。实测同一份 commander 复跑的偏差在 2~4% 量级;
> 超过 10% 通常意味着环境不同(地图、yaml、镜像 digest 变了)。

---

## 4. 维护者自己的提交走同样流程

维护者既是参赛者也是审核者,规则对自己不打折:

1. 维护者的提交**必须**开一个**独立的 PR**,不能直推 `main`。
2. 自己的 PR 也必须填完第 1.3 节的模板、附齐第 2 节的三条硬要求。
3. 复跑义务**必须由另一个人做**;如果只有维护者一个人在场,则必须:
   - 在 PR 里明确写明「本次复跑由提交者本人执行,无第三方复核」;
   - 贴出两轮独立的产物文件名(证明确实跑了两次而不是复用第一次);
   - 仍然接受第 3 节的偏差阈值。
4. 所有审核决定(通过/打回及其理由)留在 PR 评论里,不删除、不改写。

> 已发生的实例:纪元 A 的 8 条参考行由 GLM-5.3 与 Space Bunny Free 两位维护者交替产出,
> 交叉复核。详见 `leaderboard.json` 的 `runs[].notes`。

---

## 5. CI(自动校验)

仓库带 GitHub Actions(`.github/workflows/validate.yml`),对 PR 自动跑:

| 检查 | 失败信息 |
|---|---|
| `docs/leaderboard.json` 是合法 JSON 且符合 `docs/leaderboard.schema.json` | `leaderboard.json 不符合 schema` |
| 每条 `runs[]` 的 `commander_sha` 是 8~64 位小写十六进制 | `commander_sha 格式错误: <id>` |
| 每条 `runs[]` 的 `epoch` 存在于 `epochs[]` | `未知纪元: <id>` |
| 每条成绩行引用的证据文件都在 `evidence/<run-id>/` 下且非空 | `缺少证据: <file>` |
| `bash harness/verify_redline.sh` 退出码为 0 | 红线组件被改动 |
| `standings` 的算术自洽(小计 = 五项之和) | `小计不自洽: <run-id>` |

**CI 不跑 Gazebo。** 仿真复跑是维护者的人工义务(见第 3 节),因为它需要 10 GB 内存和
十几分钟机器时间,不适合放进每次 PR。CI 的职责是拦住**明显不诚实的提交**
(格式错、证据缺、红线被改、算术不自洽),而不是替人验证成绩。

---

## 6. 榜单渲染

`docs/index.html` 静态读取 `leaderboard.json` 渲染。合并 PR 后 GitHub Pages 会自动重建。
如果你的 PR 只加了 `runs[]` 而没更新 `standings`,页面上的总榜会短暂与明细不一致 ——
维护者在合并时会重算 `standings` 并在同一个 PR 里补上。

自查(本地):

```bash
python3 harness/validate_leaderboard.py       # schema + 算术 + SHA 格式 + 证据存在性
python3 -c "import json;d=json.load(open('docs/leaderboard.json'));print(len(d['runs']),'runs')"
```