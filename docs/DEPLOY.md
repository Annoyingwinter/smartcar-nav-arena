# DEPLOY.md —— 从零把打榜环境跑起来

面向**从没接触过本项目的人**(尤其是别人的 AI)。照着抄命令即可,不需要你事先懂 ROS。

- 目标环境: 宿主机 Ubuntu 22.04(其它发行版也可以,只要能跑 Docker),ROS 在容器里。
- 全程**不需要 GPU**。没 GPU 走软渲染,仿真实时比 RTF≈0.1~0.3,但**计时用的是仿真秒**(`/clock`),
  和你的机器快慢无关 —— 这是本榜单最重要的公平性前提,别用墙钟时间去比较成绩。

---

## 0. 五分钟速通(只想先看一眼跑通)

```bash
git clone https://github.com/annoyingwinter/smartcar-nav-arena smartcar-nav-arena && cd smartcar-nav-arena
bash harness/bringup_container.sh          # 建镜像(首次约 20~40 分钟)
bash harness/build_workspace.sh            # 编译 ROS 工作空间(约 2~5 分钟)
bash harness/bench_run.sh smoke 600        # 跑一轮; 车不会动, 这是故意的(见第 5 节)
python3 harness/bench_score.py smoke       # 打印 JSON, 应显示 finished=false
```

跑通了再往下读细节。

> **第一次 clone 要等一会儿。** 仓库 40 MB,体积的 92% 是大会材料 `car3` 的二进制
> 小车网格(红线组件,不能删也不能压)。实测慢速链路上首次 clone 需 35~45 分钟,
> 属正常现象 —— 建议让它在后台传,你同时做别的事。详见
> [README 的体积说明](../README.md#仓库体积与首次-clone-的耗时)。

---

## 1. 宿主机前置要求

| 项 | 要求 | 检查命令 |
|---|---|---|
| OS | Ubuntu 22.04(20.04/24.04 一般也可) | `lsb_release -a` |
| Docker | ≥ 20.10,能跑 `--cpus`/`--memory`/`--shm-size` | `docker version` |
| 磁盘 | ≥ 15 GB(镜像 ~6 GB + 工作空间编译产物 ~1 GB + 跑分产物) | `df -h .` |
| 内存 | ≥ 10 GB 可用(容器 limit 就是 10g) | `free -h` |
| CPU | ≥ 8 核(我们用 `--cpus 12`;核少会明显变慢) | `nproc` |
| GPU | **可选**。有则加 `--gpus all`,RTF 从 0.3 升到 1.0 左右 | `nvidia-smi` |

> 宿主机是 macOS / Windows? Docker Desktop 也能跑,但 bind mount 到 Linux 路径时
> 文件 IO 明显变慢,建议把仓库放在 WSL2 原生文件系统里。

---

## 2. 镜像

镜像基于 **`osrf/ros:noetic-desktop-full-focal`**,固定 digest 以保证可复现:

```
osrf/ros@sha256:f138c82f326f179e8510eb03f40ee7ccaf16538e5577ab8550af74c4e12616de
```

内含:ROS Noetic、Gazebo 11、rviz、`navigation` 系列(amcl/move_base/map_server/
gmapping/DWA)、`teleop_twist_keyboard`。`harness/Dockerfile` 在它之上只做了两件事:
装 `ros-noetic-*` 里缺的一个依赖,以及建 `flexing` 用户。

```bash
# 一条命令(推荐): 用仓库自带的脚本建镜像 + 起容器
bash harness/bringup_container.sh
# 首次会看到 "工作空间还没编译" 的警告 —— 正常, 下一步就是编译
```

<details>
<summary>手工等价命令(想理解每一步时看)</summary>

```bash
docker build -f harness/Dockerfile -t smartcar-nav-arena:noetic harness/

docker run -d --name smartcar-bench \
  --network host \
  --cpus 12 --memory 10g --shm-size 1g \
  --entrypoint /usr/local/bin/smartcar-entrypoint \
  -v "$(pwd)":/usr/local/share/arena_root \
  -v "$(pwd)/harness/smartcar-entrypoint.sh":/usr/local/bin/smartcar-entrypoint:ro \
  -e HOME=/tmp/flexhome \
  -e ARENA_ROOT=/usr/local/share/arena_root \
  smartcar-nav-arena:noetic sleep infinity
```

**每个参数为什么是它**:

| 参数 | 原因 |
|---|---|
| `--network host` | ROS 用组播/回环找 master。host 模式下不指 ROS_MASTER_URI 会互相广播,表现为"节点起了但话题空"。 |
| `--cpus 12` | Gazebo 物理 + DWA 轨迹采样是 CPU 密集。核少 RTF 掉得厉害,但**不影响计时**(仿真秒)。 |
| `--memory 10g` | ROS Noetic + Gazebo + rviz 峰值约 6~8 GB。给 10g 是实测不 OOM 的值。 |
| `--shm-size 1g` | **默认值 64 MB 会让 Gazebo 段错误**。这是最常见的"clone 下来跑不起来"原因。 |
| `-v $(pwd):/usr/local/share/arena_root` | 仓库 bind mount 进容器。宿主改代码、容器里立即生效,不用重 build。 |
| `-e HOME=/tmp/flexhome` | 家目录不在镜像里(rocker 风格)。不指 HOME 的话 gazebo 写 `~/.gazebo` 会 permission denied。 |
| `-e ARENA_ROOT=...` | entrypoint 用它定位工作空间,换挂载点时只改这一处。 |
| entrypoint 不 exit | 容器起来时 `workspace/devel/` 必然还不存在(要先编译)。entrypoint 只警告、继续活着,否则 `build_workspace.sh` 还没跑容器就没了。 |
| `sleep infinity` | 容器常驻,反复 `docker exec` 跑分,不用每轮重启。 |

</details>

---

## 3. 编译工作空间

ROS 工作空间在 `workspace/`,是标准 catkin 结构,**已在仓库里**(控制栈 5 个包;
视觉包 `yolov5_ros` / `usb_cam` / `detect_objects` / `detection_msgs` 已剔除 ——
它们与控制栈无依赖,详见第 9 节)。

```bash
bash harness/build_workspace.sh          # 默认 -j4
bash harness/build_workspace.sh -j8      # 核多就并行高一点
```

脚本会先删掉 `build/` 与 `devel/` 再编 —— 残留缓存在不同依赖集下会报很难懂的错。
预期最后一行是 `Built target ucar_commander ...`,随后它会打印容器内的
`ARENA_ROOT` / `GAZEBO_MODEL_PATH` / `rospack find ucar_commander` 供核对。

若报缺依赖:

```bash
docker exec -u root smartcar-bench bash -lc 'apt-get update && \
  apt-get install -y ros-noetic-teleop-twist-keyboard ros-noetic-navigation'
```

> `ucar_commander` 包里还有一个 **C++** 节点 `ucar_commander_node`(由 `src/commander.cpp`
> 编译而来)。打榜链路只用 Python 那个:`rosrun ucar_commander commander.py`。
> 两者互不影响,你改 Python 即可。

---

## 4. 起仿真栈(手工调试用)

跑分不需要手工起,`bench_run.sh` 会自动拉起。想手动看 rviz/Gazebo 画面时:

```bash
# 容器内, 无头(打榜用这个)
roslaunch harness/headless_nav.launch gui:=false

# 容器内, 带界面(调试用; 需要 X11 转发,见下)
roslaunch harness/headless_nav.launch gui:=true
```

带界面需要宿主机 X11:

```bash
docker run ... -e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix:ro \
                -v "$HOME/.Xauthority:/home/flexing/.Xauthority:ro" ...
xhost +si:localuser:flexing     # 宿主机执行一次
```

---

## 5. 为什么第一轮跑完"车不动"是正常的

仓库里的 `workspace/src/ucar_commander/scripts/commander.py` 是一个**占位桩**
(`baseline_commander_stub`):它只响应 `/nav_start` 发车、把机械臂归零,然后挂起。
**它不含任何导航算法,也不含任何其他模型的算法。**

所以 `bench_run.sh smoke` 跑完会看到 `finished=false` —— 这恰好证明你的环境是通的:
仿真起来了、机械臂动了、commander 注册了服务、日志和 trace 都落盘了、计分脚本能出 JSON。

确认环境通之后,下一步就是**把你自己的 commander 写进那个文件**,再按
[BENCHMARK.md](BENCHMARK.md) 跑分。

---

## 6. 端到端示例(从 clone 到第一份成绩)

```bash
# ---- 1. 拿代码 ----
git clone https://github.com/annoyingwinter/smartcar-nav-arena smartcar-nav-arena
cd smartcar-nav-arena

# ---- 2. 建镜像 + 起容器 ----
bash harness/bringup_container.sh
docker exec smartcar-bench true        # 确认容器活着

# ---- 3. 编译工作空间 ----
bash harness/build_workspace.sh

# ---- 4. 环境自测(车不动, 预期 finished=false) ----
bash harness/bench_run.sh smoke 600
python3 harness/bench_score.py smoke

# ---- 5. 写自己的算法 ----
#    编辑 workspace/src/ucar_commander/scripts/commander.py
#    (允许改的只有这个文件 + 你的辅助文件 + 5 个 nav 配置, 见 RULES.md)

# ---- 6. 跑无锥轮 A0 ----
bash harness/bench_run.sh my-A0 2400
python3 harness/bench_score.py my-A0

# ---- 7. 跑标准带锥轮 B2 (seed 7) ----
python3 harness/spawn_cones.py --dry-run --seed 7        # 留证, 打印摆放
bash harness/bench_run.sh my-B2 2400 \
  "1.419,-0.609;-0.653,-0.446;-0.422,0.892" 7
python3 harness/bench_score.py my-B2

# ---- 8. 上榜 ----
#    按 SUBMISSION.md 提 PR: 改 docs/leaderboard.json + 附证据
```

---

## 7. 排错速查

| 症状 | 原因 | 处理 |
|---|---|---|
| Gazebo 启动即段错误 | `--shm-size` 没设或太小 | 加 `--shm-size 1g` |
| `permission denied` 写 `~/.gazebo` | 没设 `HOME`,或家目录没预建 | 加 `-e HOME=/tmp/flexhome`;entrypoint 已预建三个目录 |
| 节点都起来了但话题空 | `ROS_MASTER_URI` 没指回环 | `arena_env.sh` 已兜底设成 `127.0.0.1` |
| 场地/锥桶没有碰撞、激光穿墙 | `GAZEBO_MODEL_PATH` 没指到 `env/models` | **`arena_env.sh` 会强制改指**到本仓库 `env/models`(赛事参考镜像把这个变量烤死成它自己那套目录,沿用会指向不存在的路径) |
| `ROS_MASTER_URI: unbound variable` | `docker exec` 不继承 entrypoint 的 export | 用仓库的 `harness/*.sh`;`arena_env.sh` 已兜底 |
| 节点起了但话题空 / 等不到 `/clock`,而同宿主另一轮跑得好好的 | 两个容器都用 `--network host`,抢同一个 ROS master(11311) | **串行跑轮**。真要并行:`ROS_MASTER_PORT=11312 bash harness/bench_run.sh ...`(两个变量都要设,容器也要用不同端口映射) |
| `rosrun ucar_commander commander.py` 找不到 | 工作空间没编译 | 第 3 节 |
| `/nav_start` 没注册 | commander 崩了或 4 秒内没起来 | 看 `runs/commander_<TAG>.log` |
| 卡在 `等机械臂归位 5s` 之后不动 | 计时器没点发车 | 确认用的是 `harness/run_sim.sh`(它负责点发车) |
| 容器里 `git` 报 dubious ownership | bind mount 的 UID 与容器用户不一致 | `git config --global --add safe.directory '*'` |

---

## 8. 与"现成容器"的兼容

如果你手头已经有本项目的打榜容器(不是本仓库 `Dockerfile` 建的),只要满足:

1. 仓库 bind mount 到容器内某路径;
2. `harness/smartcar-entrypoint.sh` 挂成 `/usr/local/bin/smartcar-entrypoint`;
3. 容器里有 `catkin_make` 过的 `<挂载点>/workspace/devel/setup.bash`;

就能直接用 `harness/bench_run.sh` 打分。做法:

```bash
# 假设你把仓库挂在容器的 /my/mount 上
ARENA_CONTAINER_ROOT=/my/mount SMARTCAR_CONTAINER=我的容器 \
  bash harness/build_workspace.sh
ARENA_CONTAINER_ROOT=/my/mount SMARTCAR_CONTAINER=我的容器 \
  bash harness/bench_run.sh <TAG> 2400
```

所有路径都由 `harness/arena_env.sh` 从**脚本自身位置**推导,宿主侧脚本内部再通过
`ARENA_CONTAINER_ROOT` 翻译到容器视角 —— 所以容器挂在哪都不影响宿主脚本。

### 三个必须分清的路径变量

| 变量 | 含义 | 谁在用 |
|---|---|---|
| `ARENA_ROOT` | **本进程**眼里的仓库根 | 所有脚本(在宿主上跑就是宿主路径,在容器里跑就是容器路径) |
| `ARENA_CONTAINER_ROOT` | 仓库在**容器内**的挂载点,默认 `/usr/local/share/arena_root` | 只在宿主侧的 `docker exec` 里 |
| `ARENA_MOUNT` | `ARENA_ROOT` 的别名 | 兼容旧写法,新代码用 `ARENA_ROOT` |

把它们混用会导致"宿主路径被拼进容器命令",报
`No such file or directory` —— 这是本仓库实测踩到的坑之一。

---

## 9. 仓库里没放什么（以及为什么）

| 剔除的 | 理由 |
|---|---|
| `yolov5_ros`(35 MB)、`usb_cam`、`detect_objects`、`detection_msgs` | 图像赛线的包。本榜单只打控制线;已核对这 4 个包**只互相依赖**,控制栈(car3 / ucar_navigation / ucar_commander / ucar_bringup / ucar_accumtimer)不依赖它们,所以剔除后 `catkin_make` 仍能通过。 |
| `workspace/build/`、`workspace/devel/` | 编译产物,由 `build_workspace.sh` 生成。 |
| 其余 5 份教程 PDF | 内容与本文件、`BENCHMARK.md` 高度重合;唯一的例外《控制教程》的"参数"一节经逐页核对**没有任何数值**,对基线取值无考据价值。细则原件保留在 `docs/committee/`(见该目录的版权说明)。 |
| `evidence/` 里 8 条迁移行的证据 | commander 源码与日志留在交接前的私有工作空间,未随本次建仓分发。维护者**没有伪造**这些证据,已在 `leaderboard.json` 与 `evidence/README.md` 里写明。 |

**红线组件一个都没动**:`car3`(小车模型 + `round1.world`)、`ucar_accumtimer`(计时器)、
`env/benchmark_map.pgm`(基准图)、`harness/spawn_cones.py`、`harness/bench_score.py`、
`harness/bench_monitor.py`。用 `bash harness/verify_redline.sh` 一键核对。