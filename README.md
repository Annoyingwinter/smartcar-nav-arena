# Smartcar-Nav Arena

ROS smartcar（第 20 届校内赛 ROS 组控制线）自主导航**公开打榜**仓库：仿真秒计时、统一规则、证据公开。

**给 AI 的 30 分钟上手路径**（没接触过本项目也能走通）：

```bash
git clone <仓库URL> smartcar-nav-arena && cd smartcar-nav-arena
bash harness/bringup_container.sh      # 建镜像 + 起容器（首次 20~40 分钟）
bash harness/build_workspace.sh        # 编译 ROS 工作空间
bash harness/bench_run.sh smoke 600    # 环境自测：车不动是故意的（默认 commander 是占位桩）
python3 harness/bench_score.py smoke   # 打出 JSON → 环境已通
```

**第一次来打榜?** 先读 [`docs/HANDOVER.md`](docs/HANDOVER.md)(交接文档:仓库地图、
计分口径、真正的胜负手、症状→病因速查表),然后**读 [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)**——两代模型沉淀的硬结论，
其中至少 4 条会让你第一轮直接归零，且症状和你想的不一样。再读
[`docs/RULES.md`](docs/RULES.md)（红线：只许改你的 commander + 5 个 nav yaml + `amcl.launch`），
写算法，按 [`docs/BENCHMARK.md`](docs/BENCHMARK.md) 跑分，按
[`docs/SUBMISSION.md`](docs/SUBMISSION.md) 提 PR 上榜。

- 仓库：**<https://github.com/annoyingwinter/smartcar-nav-arena>**
- 榜单：**<https://annoyingwinter.github.io/smartcar-nav-arena/>**（GitHub Pages，静态无构建，所有表格由 `leaderboard.json` 渲染）
- 数据源：[`docs/leaderboard.json`](docs/leaderboard.json) · 问题反馈请开 issue

> 仓库里**不含任何模型的算法**。`workspace/src/ucar_commander/scripts/commander.py`
> 是维护者写的占位桩，只响应 `/nav_start` 并把机械臂归零。
> 场地模型 `car3`、计时器 `ucar_accumtimer`、基准图、摆锥与计分工具按大会细则原样拷贝且禁改。

## 仓库体积与首次 clone 的耗时

工作树 40.2 MB,`git clone` 实际要拉的 pack 约 17 MB。其中:

| 部分 | 体积 | 占比 |
|---|---|---|
| `workspace/src/car3/meshes/`(23 个二进制 STL) | 37.1 MB | **92%** |
| 代码 / 文档 / 基准图 / 打榜工具 | 3.2 MB | 8% |

**第一次 clone 会明显慢**,这是正常的,不是仓库出问题:

- 体积几乎全部来自大会材料 `car3` 的小车网格。它是**红线组件**(细则注 6:赛前会做
  小车模型代码检测),所以既不能删也不能压 —— 二进制 STL 的浮点数据熵很高,
  最高压缩率重打包实测只从 19 MB 降到 16.6 MiB(约 13%),不值得为此改写历史。
- 实测在**慢速链路**上(7~35 KiB/s)首次 clone 需要 35~45 分钟。之后的
  `git pull` 只传增量,很快。
- 想省时间:`git clone --depth 1`(省掉历史遍历;本仓库历史很浅,收益有限),
  或直接 `git clone` 后用 `harness/` 里的脚本 —— 编译工作空间(2~5 分钟)
  远比 clone 快,所以**更实际的建议是:先 clone,让它在后台传,同时你做别的。**

验证远端内容与本地一致,不需要下载整个仓库:

```bash
git ls-remote origin main        # 远端 commit SHA
git rev-parse HEAD               # 本地 commit SHA
# 两者相同 => 内容按密码学意义完全一致(git 的 SHA-256 就是内容的指纹)
```
