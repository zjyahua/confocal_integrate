# Confocal Integrate — 共聚焦显微镜实验控制软件

基于 **Python 3.9 + PyQt5** 的共聚焦荧光显微镜一体化控制软件，用于金刚石 NV 色心 / 单光子源的
共聚焦成像、脉冲 ESR（ODMR / Rabi / Ramsey / Spin-echo / T1）与荧光寿命测量。

> An integrated PyQt5 control suite for confocal microscopy, pulsed ODMR and
> lifetime measurements on NV centers.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 功能

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 共聚焦扫描 | `src/interface/confocal_scan.py` | 二维 / 三维点扫描成像，振镜 + 压电位移台 |
| 图像处理 | `src/interface/scan_image_deal.py` | 扫描图像后处理与显示 |
| 脉冲序列 | `src/interface/sequence.py` | 载入 `config/PulseSeq/*` 波形，驱动 Pulse Streamer |
| 单点脉冲 ESR | `src/interface/single_point_exp.py` | 脉冲 ODMR 单点测量 |
| 荧光寿命 | `src/interface/lifetime.py` | 寿命扫描、拟合与频率列表 |
| 自动跟踪 | `src/interface/track.py` | 长时间测量的位置跟踪与补偿 |
| 数据拟合 | `src/fitting_method/` | 寿命拟合、正弦（Rabi/Ramsey）拟合 |

支持的脉冲序列：`cw_odmr`、`pulse_odmr`、`rabi`、`ramsey`、`spin_echo`、`T1`、`lifetime`。

## 硬件

| 设备 | 用途 | 封装位置 |
| --- | --- | --- |
| PI E7273 CDA | 压电位移台（x/y/z 扫描与定位） | `src/hardware/PI_E7273_CDA` |
| Galvanometer | 振镜快速扫描 | `src/hardware/Galvanometer` |
| Swabian Pulse Streamer | 脉冲序列输出 | `src/hardware/Swabian_Pulse_Streamer` |
| Swabian Time Tagger Ultra | 光子计数 / 时间标记 | `src/hardware/Swabian_TimeTaggerUltra` |
| Windfreak SynthHD | 微波源（ODMR 磁场 / 频率扫描） | `src/hardware/Synth_HD` |

所有设备由 `src/hardware/__init__.py` 中的 `DeviceManager` 统一初始化与释放。

## 目录结构

```
confocal_integrate/
├── main.py                  # 程序入口（主窗口）
├── config/                  # YAML 参数与脉冲序列波形
│   └── PulseSeq/            # cw_odmr / pulse_odmr / rabi / ramsey / spin_echo / T1 / lifetime
├── src/
│   ├── hardware/            # 各仪器 API 封装 + DeviceManager
│   ├── interface/           # 各实验界面逻辑
│   ├── threads/             # 测量线程（扫描、寿命、跟踪等）
│   ├── fitting_method/      # 拟合算法
│   └── utils/               # 日志、数据处理工具
├── ui/                      # Qt Designer 生成的界面代码与 .ui 文件
└── requirements.txt
```

## 安装

```bash
# 建议使用 Python 3.9
conda create -n confocal python=3.9
conda activate confocal

pip install -r requirements.txt
```

说明：

- `TimeTagger` 通常需要从 [Swabian Instruments](https://www.swabianinstruments.com/) 官网下载对应
  Python 版本的安装包；`pulsestreamer` 亦为同厂商 SDK。
- `pipython` 需要 PI 的 GCS DLL；`windfreak` 通过串口（默认 `COM3`）连接 SynthHD。
- 无硬件时程序仍可启动，但各实验界面会提示设备连接失败。

## 运行

```bash
python main.py
```

启动后先在各界面中连接设备，再载入 `config/` 下的参数与波形开始测量。

## 配置

- `config/config_confocal*.yaml`：扫描范围、步长、驻留时间等参数
- `config/config_lifetime*.yaml`：寿命测量与拟合参数
- `config/PulseSeq/*.txt`：Pulse Streamer 序列波形文件

> `config/env_config.yaml` 仅用于本地 IDE 解释器配置，已被 `.gitignore` 排除。

## 注意

- 本项目面向实验室内部仪器环境，`src/hardware/__init__.py` 中默认写入了本机设备的序列号
  （Pulse Streamer / Time Tagger），在其它机器上使用时请修改为自己的设备序列号。
- 日志写入 `logs/`，运行缓存写入 `cache/`，二者均不纳入版本控制。

## License

本项目采用 [MIT License](LICENSE) 发布，可自由使用、修改与分发，仅需保留版权声明。

Copyright (c) 2026 zjyahua
