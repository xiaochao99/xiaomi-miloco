# Xiaomi Bridge 使用说明

## 概述

Xiaomi Bridge 是一个用于连接小爱音箱和 Miloco AI 的桥接服务，实现语音唤醒、语音识别和语音合成功能。

**功能特性：**

- ✅ 通过唤醒词（如"小米同学"）唤醒小爱音箱进入 Miloco 对话模式
- ✅ 支持本地语音识别（ASR）
- ✅ 支持语音合成（TTS）播放回复
- ✅ 支持连续对话模式
- ✅ 提供 WebSocket 接口用于音频流传输

## 目录结构

```
xiaomi_bridge/
├── config.py              # 配置管理
├── manager.py             # 桥接管理器
├── conversation.py        # 对话控制器
├── vad.py                 # 语音活动检测
├── kws.py                 # 关键词检测
├── asr.py                 # 语音识别
├── tts.py                 # 语音合成
├── audio_stream.py        # 音频流管理
└── services/              # 服务层（重构代码）
    ├── audio/             # 音频服务
    └── protocols/         # 协议层
```

## 快速开始

### 1. 安装依赖

```bash
# 安装项目依赖
pip install -e miloco_server/

# 安装额外依赖（如未自动安装）
pip install onnxruntime numpy sherpa-onnx httpx
```

### 2. 下载模型文件

需要下载以下模型文件并放置到指定目录：

**VAD 模型（语音活动检测）:**

- `models/vad/silero_vad.onnx`

**KWS 模型（关键词检测）:**

- `models/kws/encoder.onnx`
- `models/kws/decoder.onnx`
- `models/kws/joiner.onnx`
- `models/kws/tokens.txt`

**ASR 模型（语音识别）:**

- `models/asr/model.int8.onnx`（或 `model.onnx`）
- `models/asr/decoder.onnx`
- `models/asr/joiner.onnx`
- `models/asr/tokens.txt`

### 3. 配置环境变量

```bash
# 启用 Xiaomi Bridge
export MILOCO_BRIDGE_ENABLED=1

# 可选配置
export MILOCO_WAKEUP_KEYWORDS="小米同学"
export MILOCO_TTS_ENGINE="doubao"
export MILOCO_DOUBAO_APP_ID="your_app_id"
export MILOCO_DOUBAO_ACCESS_KEY="your_access_key"
```

### 4. 启动服务

```bash
# 使用启动脚本
python start_bridge.py

# 或使用调试模式
python start_bridge.py --debug
```

## 配置说明

### 环境变量配置

| 变量名                        | 说明                 | 默认值                          |
| -------------------------- | ------------------ | ---------------------------- |
| `MILOCO_BRIDGE_ENABLED`    | 是否启用 Xiaomi Bridge | `0`（禁用）                      |
| `MILOCO_WAKEUP_KEYWORDS`   | 唤醒词，逗号分隔           | `小米同学`                       |
| `MILOCO_EXIT_KEYWORDS`     | 退出关键词，逗号分隔         | `退出,结束对话,停止`                 |
| `MILOCO_VAD_THRESHOLD`     | VAD 阈值（0-1）        | `0.10`                       |
| `MILOCO_VAD_MIN_SPEECH`    | 最小语音时长（ms）         | `250`                        |
| `MILOCO_VAD_MIN_SILENCE`   | 最小静音时长（ms）         | `500`                        |
| `MILOCO_KWS_SCORE`         | KWS 分数阈值           | `2.0`                        |
| `MILOCO_KWS_THRESHOLD`     | KWS 检测阈值           | `0.2`                        |
| `MILOCO_ASR_MODEL`         | ASR 模型类型           | `sense_voice`                |
| `MILOCO_ASR_INT8`          | 是否使用 INT8 量化       | `1`（启用）                      |
| `MILOCO_TTS_ENGINE`        | TTS 引擎             | `doubao`                     |
| `MILOCO_DOUBAO_APP_ID`     | 豆包 TTS App ID      | 空                            |
| `MILOCO_DOUBAO_ACCESS_KEY` | 豆包 TTS Access Key  | 空                            |
| `MILOCO_DOUBAO_VOICE`      | 豆包语音 ID            | `zh_female_vv_uranus_bigtts` |
| `MILOCO_WAKEUP_TIMEOUT`    | 唤醒超时时间（秒）          | `20`                         |
| `MILOCO_WS_PORT`           | WebSocket 端口       | `4399`                       |
| `MILOCO_AUDIO_GAIN`        | 音频增益               | `1.0`                        |

### 配置文件

也可以通过 `BridgeConfig` 类进行编程配置：

```python
from miloco_server.xiaomi_bridge.config import BridgeConfig

config = BridgeConfig(
    enabled=True,
    kws=KWSConfig(
        keywords=["小米同学", "你好小米"],
        model_dir="models/kws"
    ),
    tts=TTSConfig(
        engine="doubao",
        app_id="your_app_id",
        access_key="your_access_key"
    )
)
```

## API 接口

### REST API

#### 获取状态

```http
GET /api/xiaomi-bridge/status
```

响应示例：

```json
{
    "enabled": true,
    "active": false,
    "state": "idle"
}
```

#### 手动唤醒

```http
POST /api/xiaomi-bridge/wakeup
Content-Type: application/json

{
    "text": "小米同学"
}
```

#### 发送文本

```http
POST /api/xiaomi-bridge/text
Content-Type: application/json

{
    "text": "今天天气怎么样？"
}
```

#### 停止对话

```http
POST /api/xiaomi-bridge/stop
```

#### 更新配置

```http
POST /api/xiaomi-bridge/config
Content-Type: application/json

{
    "wakeup_keywords": ["小米同学", "你好"],
    "exit_keywords": ["退出", "停止"]
}
```

### WebSocket 接口

Xiaomi Bridge 启动时会在 **4399 端口**启动一个独立的 WebSocket 服务器，用于接收小爱音箱的音频流。

#### 音频流端点（独立端口）

```
ws://localhost:4399/
```

**发送数据：**

- 二进制帧：PCM 音频数据（16kHz, 16-bit, mono）

#### 备用端点（主服务端口）

同时也支持通过主服务端口访问（需要认证）：

```
wss://localhost:443/api/xiaomi-bridge/ws/audio?client_id=speaker001
```

**注意：** 小爱音箱 Rust Client 默认连接 `ws://server-ip:4399`，请确保 4399 端口已开放。

**接收数据：**

- 二进制帧：TTS 音频数据

## 小爱音箱连接

### 使用 Rust Client 连接

小爱音箱通过 WebSocket 连接到 Xiaomi Bridge：

```rust
use tokio_tungstenite::connect_async;
use tungstenite::Message;

async fn connect_to_bridge() -> Result<(), Box<dyn std::error::Error>> {
    let url = "ws://bridge-host:4399/api/xiaomi-bridge/ws/audio?client_id=my_speaker";
    let (ws_stream, _) = connect_async(url).await?;
    
    // 发送音频数据
    let audio_data = get_audio_from_microphone().await?;
    ws_stream.send(Message::Binary(audio_data)).await?;
    
    Ok(())
}
```

### 音频格式要求

- **采样率**: 16000 Hz
- **位深**: 16-bit (int16)
- **通道数**: 1 (mono)
- **格式**: PCM（无压缩）

## 对话流程

```
┌─────────────────────────────────────────────────────────────┐
│                    对话流程示意                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  小爱音箱                                                    │
│      │                                                      │
│      │ 发送音频流                                            │
│      ▼                                                      │
│  ┌──────────────┐    检测到唤醒词    ┌──────────────────┐    │
│  │   KWS 模块   │ ─────────────────→ │   对话控制器     │    │
│  └──────────────┘                    └────────┬─────────┘    │
│         │                                     │              │
│         │ 持续监听                             │ 进入对话模式  │
│         ▼                                     ▼              │
│  ┌──────────────┐                    ┌──────────────────┐    │
│  │   VAD 模块   │ ──语音结束───→     │   ASR 语音识别   │    │
│  └──────────────┘                    └────────┬─────────┘    │
│                                               │              │
│                                               ▼              │
│                                    ┌──────────────────┐      │
│                                    │   Miloco AI      │      │
│                                    └────────┬─────────┘      │
│                                               │              │
│                                               ▼              │
│                                    ┌──────────────────┐      │
│                                    │   TTS 语音合成   │      │
│                                    └────────┬─────────┘      │
│                                               │              │
│                                               ▼              │
│                                        小爱音箱播放回复        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 测试命令

### 检查模型文件

```bash
python start_bridge.py --check-only
```

### 列出所需模型

```bash
python start_bridge.py --list-models
```

### 测试重构代码

```bash
cd miloco_server
python -m xiaomi_bridge.test_bridge
```

## 常见问题

### 1. 模型文件缺失

**问题**: 启动时提示缺少模型文件

**解决**: 请按照"下载模型文件"部分的说明下载并放置模型文件

### 2. 唤醒词不生效

**问题**: 说唤醒词后没有反应

**检查项**:

- 确认 `MILOCO_BRIDGE_ENABLED=1`
- 检查麦克风是否正常工作
- 确认模型文件正确
- 检查日志输出

### 3. TTS 无声音

**问题**: Miloco 有回复但没有声音

**检查项**:

- 确认 TTS 配置正确（App ID 和 Access Key）
- 检查网络连接（豆包 TTS 需要联网）
- 检查音频输出设备

### 4. WebSocket 连接失败

**问题**: 小爱音箱无法连接到 Bridge

**检查项**:

- 确认 Bridge 服务正在运行
- 检查端口 `4399` 是否被占用
- 确认防火墙允许连接

## 日志说明

日志级别可通过环境变量 `MILOCO_LOG_LEVEL` 设置：

- `debug`: 详细调试信息
- `info`: 一般信息
- `warning`: 警告信息
- `error`: 错误信息

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      API 层                                 │
│  REST API + WebSocket                                       │
├─────────────────────────────────────────────────────────────┤
│                   控制器层                                   │
│  BridgeManager ─→ ConversationController                    │
├─────────────────────────────────────────────────────────────┤
│                   服务层                                     │
│  VAD (语音检测) → KWS (关键词) → ASR (识别) → TTS (合成)    │
├─────────────────────────────────────────────────────────────┤
│                    协议层                                    │
│  WebSocket 音频流协议                                        │
└─────────────────────────────────────────────────────────────┘
```

## 许可证

Copyright (C) 2025 Xiaomi Corporation

This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
