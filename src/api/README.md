# 实验控制 API（headless）

目标：同一个控制面同时服务两种场景。

- **UI 关着**：CLI 直接跑（无窗口），把图渲染成 PNG，在对话里贴给用户。
- **UI 开着**：CLI 把命令转发给 GUI 里的控制服务，参数回填到界面、扫描在界面上实时显示。

## 结构

```
        ┌──────────────────────────────┐
        │  src/api/jobs.JobRunner      │  任务表 + 执行（单硬件锁）
        └──────────┬───────────────────┘
                   │ executor(job)
     ┌─────────────┴──────────────┐
     │                            │
main.py (Qt, 宿主)          cli.py (无窗口)
  ├─ 控制服务嵌入              ├─ 找不到服务 → 本地执行
  ├─ 参数回填 UI               └─ 输出 JSON / PNG
  └─ 数据画到窗口
```

| 文件 | 职责 |
| --- | --- |
| `models.py` | `Job` 数据结构与状态常量 |
| `plan.py` | 参数校验、波形构建、段数与耗时估计（**不碰硬件**） |
| `jobs.py` | 后台执行、进度、停止、互斥锁 |
| `render.py` | matplotlib Agg → PNG（扫描图、曲线、直方图） |
| `server.py` | localhost HTTP 控制服务（可嵌入 GUI，也可独立运行） |
| `client.py` | CLI 用的轻量客户端 |
| `cli.py` | 命令行入口 |

## 命令行

```bash
# 只做规划，不碰硬件
python -m src.api.cli scan  --mode intensity --dwell-ms 0.05 --resolution 100 --dry-run
python -m src.api.cli point --mode freq --start 2800 --end 2940 --step 1 \
                            --loops 10 --average 10000 --dry-run

# 点测量只有三种组合（没有 freq + Histogram）
python -m src.api.cli point --mode freq --count-mode Gate \
    --sequence pulse_odmr/Pulse_ODMR_130ns.txt \
    --start 2800 --end 2940 --step 1 --loops 10 --average 5000

python -m src.api.cli point --mode time --count-mode Gate \
    --sequence T1/T1_no_mw.txt \
    --start 1 --end 5000 --points 100 --time-scale Exponential \
    --loops 10 --average 5000

python -m src.api.cli point --mode time --count-mode Histogram \
    --sequence rabi/Rabi_130ns_histogram.txt \
    --bin-width 100 --bin-num 1000 --loops 10 --average 5000

# 点测量 + 自动追踪：ref 低于阈值时先跑一次 track 再继续
python -m src.api.cli point --mode time --count-mode Gate \
    --sequence T1/T1_no_mw.txt \
    --start 1 --end 5000 --points 100 --time-scale Exponential \
    --loops 10 --average 5000 \
    --auto-track --track-threshold 3000 --track-step 0.0025 --track-z-step 0.1

# 自动找最亮点（会移动样品！laser_on 才开激光，结束后恢复）
python -m src.api.cli track --step 0.0025 --z-step 0.1 --integral-ms 200 --laser-on

# 定位：读当前位置 / 移动到某点（X/Y 是 galvo 电压，Z 是位移台 µm）
python -m src.api.cli where
python -m src.api.cli goto --x -0.479 --y 0.204
python -m src.api.cli goto --dx 0.01 --dy 0.01
python -m src.api.cli goto --scan "<扫描输出目录>" --row 95 --col 71
python -m src.api.cli goto --z 49.1

# 控制服务（UI 未开时可选；不开也能跑，CLI 会本地执行）
python -m src.api.cli serve --port 8765

# 任务查询
python -m src.api.cli status
python -m src.api.cli result --job <job_id>
python -m src.api.cli stop   --job <job_id>

# 渲染演示
python -m src.api.cli demo --out experiments/demo
```

`--json` 输出机器可读结果，便于 agent 解析。

## 自动拟合

点测量结束后可以直接拟合（模型移植自 `data_processing/Fitting_methods`）：

| `--fit` | 适用 | 输出参数 |
| --- | --- | --- |
| `lorentz` | ODMR 吸收峰（自动找峰，最多 8 个） | 每个峰的 center / fwhm / amplitude、background |
| `rabi` | Rabi 振荡 | amplitude、frequency_mhz、period_ns、phase、t2_ns、offset |
| `t1` | T1 弛豫 | amplitude、t1_ns、offset |
| `t2` | T2 弛豫（stretched） | amplitude、t2_ns、beta、offset |
| `fid` | Ramsey / FID | amplitude、frequency_mhz、period_ns、t2_star_ns、n、offset |

```bash
# ODMR：拟合 sig/ref 比值，默认自动找峰
python -m src.api.cli point --mode freq --count-mode Gate \
    --sequence pulse_odmr/Pulse_ODMR_130ns.txt \
    --start 2800 --end 2940 --step 1 --loops 10 --average 5000 \
    --fit lorentz

# 指定峰数 / 换拟合列
--fit lorentz --fit-peaks 2 --fit-column ratio|sig|ref

# T1
python -m src.api.cli point --mode time --count-mode Gate \
    --sequence T1/T1_no_mw.txt --start 1 --end 100000 --points 60 \
    --time-scale Exponential --loops 10 --average 5000 --fit t1
```

拟合失败不会让扫描失败：结果里会写 `"fit": {ok: false, error: ...}`。
成功时写 `fit.png`（数据 + 拟合曲线 + 参数框）和 `summary.json` 的 `fit` 段。

## 本地任务历史

没有控制服务时，`status` / `result` 读仓库根目录的 `.api_jobs.json`（已 gitignore，
保留最近 50 条），所以 CLI 前台跑完的任务也能查：

```bash
python -m src.api.cli status                  # 最近的本地任务
python -m src.api.cli status --job <job_id>   # 单个任务：summary + 文件列表
python -m src.api.cli result --job <job_id>   # 文件绝对路径
```

有服务在跑时优先用服务的任务表；`stop` 仍然只支持服务模式（本地任务就在当前
进程里前台运行）。

## 实时进度（live view）

扫描运行期间，输出目录里会不断刷新两个文件：

```
live.png    当前的曲线 / 直方图 / 部分扫描图（每 --live-interval 秒重画，默认 2 s）
live.json   { phase, loop, loop_num, point, point_num, elapsed_s, eta_s }
```

同时 stdout 每 `--live-interval` 秒打印一行：

```
[live] loop 2/4 point 16/40  elapsed 16.1s  eta 29.8s
```

`--live-interval 0` 关闭实时输出。agent 可以在扫描过程中读 `live.png` 贴图，
也可以在结束时用 `status --job` / `--json` 看最终进度。

## 输出位置

每天一个文件夹，**只有四类顶层目录**，不再每次调用都堆一个新文件夹：

```
C:/zjh/experiment data/<YYYY.MM.DD>/
├── logs/            每个类别一个带时间戳的日志文件
│   ├── scan.log     START / PLAN / END + 参数和结果摘要
│   ├── track.log
│   ├── point.log
│   └── misc.log     goto / where / demo
├── scan/            共聚焦扫描，每次运行一个子文件夹
├── track/           追踪，每次运行一个子文件夹
└── point/           单点实验，每次运行一个子文件夹
```

`goto` / `where` / `demo` **不创建数据文件夹**，只写日志。

用 `CONFOCAL_DATA_ROOT` 环境变量可以改根目录，`--out` 可以指定具体目录。

每次运行的子文件夹：

```
<out_dir>/
├── params.json     提交时的参数快照
├── plan.json       校验与规划结果（段数、耗时估计）
├── summary.json    结束时的摘要（拟合参数/错误）
├── raw.txt         逐 loop 原始数据
├── average.txt     各 loop 平均后的曲线（画图/拟合用）
├── image.png / sweep.png / histogram.png / fit.png / track.png
└── live.png / live.json（运行中的实时快照）
```

`raw.txt` 的列（和 DataThread 的存储一致）：

| 实验 | 列 |
| --- | --- |
| Gate（freq/time） | `loop  point  <freq_mhz/time_ns>  sig  ref  valid` |
| Histogram | `loop  bin  time_ns  counts` |
| 共聚焦扫描 | `x  y  counts`（单次扫描，没有 loop） |

## HTTP 契约

服务只监听 `127.0.0.1`，端口与 token 写在仓库根目录的 `.api_port` / `.api_token`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | `{ok, gui, jobs}` |
| POST | `/jobs` | `{kind, params, out_dir, dry_run}` → Job |
| GET | `/jobs?limit=N` | 最近任务列表 |
| GET | `/job?job_id=X` | 单个任务 |
| GET | `/result?job_id=X` | 任务 + 文件绝对路径 |
| POST | `/stop` | `{job_id}` |

所有请求需带 `X-Api-Token` 头。

## 接入 Qt 界面

`main.py` 里创建服务，并把执行器指向 Qt 线程：

```python
from src.api.jobs import JobRunner
from src.api.server import start_service

class mainGUI(...):
    def __init__(self):
        ...
        self.api_runner = JobRunner(executor=self.api_execute_job)
        self.api_server, self.api_thread, self.api_port = start_service(
            self.api_runner, gui=self
        )

    def api_execute_job(self, job):
        """在 worker 线程被调用：切回 Qt 主线程执行并等待结果。"""
        return self._call_on_gui_thread(lambda: self._run_job_on_gui(job))

    def _run_job_on_gui(self, job):
        # 1) job.params 回填到界面控件（让操作者看到 AI 设了什么）
        # 2) 调用界面里“开始”按钮走的同一个函数
        # 3) 等待扫描线程结束
        # 4) 返回 summary dict
```

`_call_on_gui_thread` 可以用一个信号 + 事件实现：

```python
job_call = QtCore.pyqtSignal(object)
...
self.job_call.connect(self._handle_job_call)   # 跨线程自动排队

def _call_on_gui_thread(self, fn):
    box, done = {}, threading.Event()
    self._pending = (fn, box, done)
    self.job_call.emit(None)
    done.wait()
    return box.get("value")
```

## 当前状态

- ✅ `plan`：两类任务的参数校验、波形构建、段数与耗时估计
- ✅ `jobs`：后台执行、状态机、输出落盘、硬件互斥锁
- ✅ `server` / `client` / `cli`：三种运行方式（本地、独立服务、GUI 内嵌）
- ✅ `render`：扫描图、扫描曲线、直方图（无需 Qt）
- ✅ `execute`：共聚焦**强度扫描**已接真机（`ConfocalScanThread` + `DataThread`，
  无需 Qt 窗口），输出 `raw.txt` / `image.png` / `summary.json`
- ✅ `execute`：**点测量**已接真机，支持三种组合（`freq + Gate`、
  `time + Gate`、`time + Histogram`），输出 `raw.txt` / `sweep.png` 或
  `histogram.png` / `summary.json`（含峰位、均值、对比度）
- ✅ `--z` 缺省时读取位移台当前位置，不会擅自移动 Z
- ✅ `execute`：**track** 已接真机（`MaxThread`），**位移布局固定**：
  X/Y 用 galvo（步长 `--step`，单位 V），Z 用压电位移台（步长 `--z-step`，单位 µm）；
  输出 `track.png`（三轴曲线，标注起点/终点）/ `summary.json`（origin、final、峰值）
- ✅ **定位**：`goto`（绝对 / 相对 / 按扫描图像像素）和 `where`（只读当前位置），
  坐标系同上；带 galvo ±10 V、Z 0–100 µm 的安全限制
- ✅ `track` 支持 `--laser-on`：运行期间打开激光，结束后恢复（不给就要求激光已开）
- ✅ **自动拟合**：`--fit lorentz|rabi|t1|t2|fid`，输出 `fit.png` + `summary.json` 的 `fit` 段
- ✅ **本地任务历史**：`.api_jobs.json` 记录每个 job，无服务时 `status` / `result` 可用
- ✅ **实时进度**：点测量与共聚焦扫描运行期间每隔 `--live-interval` 秒刷新
  `live.png` / `live.json`，并打印 `[live]` 进度行（含 ETA）
- ✅ **点测量 + 自动追踪**：`--auto-track --track-threshold N`，ref 低于阈值时
  在 headless 下直接跑 `MaxThread` 找点（相当于 GUI 的 track 窗口），
  追踪记录写进 `summary.json` 的 `track_events`
- ⏳ 时间扫描（FLIM）执行器还没接
- ⏳ Qt 界面内嵌控制服务（参数回填 + 界面实时显示）还没接
