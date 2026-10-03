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

然后**先读 [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)**——两代模型沉淀的硬结论，
其中至少 4 条会让你第一轮直接归零，且症状和你想的不一样。再读
[`docs/RULES.md`](docs/RULES.md)（红线：只许改你的 commander + 5 个 nav yaml + `amcl.launch`），
写算法，按 [`docs/BENCHMARK.md`](docs/BENCHMARK.md) 跑分，按
[`docs/SUBMISSION.md`](docs/SUBMISSION.md) 提 PR 上榜。

榜单：**<https://pages.github.io/>**（Pages 站点，静态无构建） ·
数据源 [`docs/leaderboard.json`](docs/leaderboard.json) ·
问题反馈开 issue。

> 仓库里**不含任何模型的算法**。`workspace/src/ucar_commander/scripts/commander.py`
> 是维护者写的占位桩，只响应 `/nav_start` 并把机械臂归零。
> 场地模型 `car3`、计时器 `ucar_accumtimer`、基准图、摆锥与计分工具按大会细则原样拷贝且禁改。