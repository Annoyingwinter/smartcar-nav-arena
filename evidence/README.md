# evidence/ —— 成绩行的证据

每条 `docs/leaderboard.json` 里的 `runs[]` 记录，对应本目录下的一个子目录，
目录名 = 该行的 `id`。

```
evidence/
└── <run-id>/
    ├── commander.py              必需 —— 跑分时那一版 commander 的完整源码(原样)
    ├── trace.csv                 必需 —— bench_monitor 的 5Hz 采样, 非空
    ├── commander_<TAG>.log       跑分时 commander 的 stdout
    ├── sim_run_<TAG>.log         总控日志, 必须含「耗时: 墙钟 X s / 仿真 Y s」
    ├── sim_nodes_<TAG>.log       导航栈 stderr(可选, 但排错很有用)
    ├── cones.txt                 带锥轮的 spawn_cones.py --dry-run 输出
    ├── nav_calib.py 等            你自建的辅助文件(如有)
    └── config/                   你改动过的 nav yaml 副本(如有)
    └── <你自建的其他文件>
```

## 为什么这些必须进仓库

SHA 只能告诉你"是哪一份",不能让你**读**它。审稿人要判断你的算法是否值得这个分数、
是否能被复现，就必须拿到源码本身。只给 SHA 不给源码的 PR 会被直接打回
（见 [`../docs/SUBMISSION.md`](../docs/SUBMISSION.md) 第 2 节）。

## 现状

`leaderboard.json` 里现有的 8 条**迁移参考行**（纪元 A）**没有**证据目录 ——
它们的 commander 源码与日志留在交接前的私有工作空间里，未随本次建仓分发。
维护者**没有**伪造证据，也没有替这些行补造 `trace.csv`。

这一点已在 `leaderboard.json` 的 `disclosure` 里写明。若你能拿到那些产物，
欢迎提 PR 补进本目录（补齐后请把 `runs[].evidence` 设为 `evidence/<id>/`）。