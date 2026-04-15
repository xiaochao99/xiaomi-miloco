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

# 可选配置（统一 TTS 接口，根据引擎自动路由）
export MILOCO_WAKEUP_KEYWORDS="小米同学"

# 1) 使用豆包
export MILOCO_TTS_ENGINE="doubao"
export MILOCO_DOUBAO_APP_ID="your_app_id"
export MILOCO_DOUBAO_ACCESS_KEY="your_access_key"

# 2) 使用 MiMo
# export MILOCO_TTS_ENGINE="mimo"
# export MILOCO_MIMO_API_KEY="your_mimo_api_key"
# export MILOCO_MIMO_API_URL="https://api.xiaomimimo.com"
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
| `MILOCO_TTS_ENGINE`        | TTS 引擎（`doubao` / `mimo` / `xiaoai`） | `doubao`                     |
| `MILOCO_DOUBAO_APP_ID`     | 豆包 TTS App ID      | 空                            |
| `MILOCO_DOUBAO_ACCESS_KEY` | 豆包 TTS Access Key  | 空                            |
| `MILOCO_MIMO_API_KEY`      | MiMo TTS API Key     | 空                            |
| `MILOCO_MIMO_API_URL`      | MiMo TTS API 地址      | `https://api.xiaomimimo.com` |
| `MILOCO_DOUBAO_VOICE`      | 豆包语音 ID            | `zh_female_vv_uranus_bigtts` |
| `MILOCO_XIAOMI_BRIDGE_API_AUTH` | Xiaomi Bridge API 鉴权开关（`1` 开启，`0` 关闭） | `1` |
| `MILOCO_XIAOMI_BRIDGE_PUBLIC_ENDPOINTS` | Xiaomi Bridge 匿名白名单端点（逗号分隔，路由键） | `health,status` |
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

鉴权说明：

- 默认开启 Xiaomi Bridge API 鉴权：`MILOCO_XIAOMI_BRIDGE_API_AUTH=1`
- 默认匿名白名单仅包含 `health,status`
- 其余接口（含 `/tts`、`/play/*`、`/wakeup`、`/interrupt`、`/devices`、`/ws/play_stream`）需要携带 JWT 或 API Token
- `MILOCO_XIAOMI_BRIDGE_PUBLIC_ENDPOINTS` 使用路由键，不带前缀，例如：
  - `health,status`
  - `health,status,ws/play_stream`

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

#### 统一 TTS（唯一接口）

> 当前只保留统一 TTS 接口，不再区分 `/tts/doubao`、`/tts/mimo`。
> 实际走哪个引擎由环境变量 `MILOCO_TTS_ENGINE` 决定。

```http
POST /api/xiaomi-bridge/tts
Content-Type: application/json

{
    "text": "你好，我是小爱语音助手",
    "speaker_id": "zh_female_vv_uranus_bigtts"
}
```

```http
POST /api/xiaomi-bridge/tts/stream
Content-Type: application/json

{
    "text": "这是一段流式播报测试",
    "speaker_id": "zh_female_vv_uranus_bigtts"
}
```

响应示例：

```json
{
    "code": 0,
    "message": "ok",
    "engine": "doubao"
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

- 确认 `MILOCO_TTS_ENGINE` 配置正确（`doubao` 或 `mimo`）
- 若 `doubao`：检查 `MILOCO_DOUBAO_APP_ID` 和 `MILOCO_DOUBAO_ACCESS_KEY`
- 若 `mimo`：检查 `MILOCO_MIMO_API_KEY`（可选 `MILOCO_MIMO_API_URL`）
- 检查网络连接（豆包/MiMo 都需要联网）
- 检查音频输出设备

### 4. WebSocket 连接失败

**问题**: 小爱音箱无法连接到 Bridge

**检查项**:

- 确认 Bridge 服务正在运行
- 检查端口 `4399` 是否被占用
- 确认防火墙允许连接

### 5. Xiaomi Bridge 接口返回 401/WS 1008

**问题**: 调用 `/api/xiaomi-bridge/*` 返回未授权，或 `ws/play_stream` 连接被关闭。

**检查项**:

- 确认是否开启鉴权（默认开启）：`MILOCO_XIAOMI_BRIDGE_API_AUTH=1`
- 请求是否携带认证信息：
  - HTTP: `Authorization: Bearer <token>`
  - WebSocket: query 参数 `?token=<token>` 或 cookie
- 若需匿名访问，确认端点已加入 `MILOCO_XIAOMI_BRIDGE_PUBLIC_ENDPOINTS`
- 临时联调可设 `MILOCO_XIAOMI_BRIDGE_API_AUTH=0`（仅建议内网）

## 生产环境推荐配置

```bash
# 强烈建议：开启鉴权（默认）
export MILOCO_XIAOMI_BRIDGE_API_AUTH=1

# 匿名白名单最小化，仅保留探活
export MILOCO_XIAOMI_BRIDGE_PUBLIC_ENDPOINTS="health,status"

# 生产环境优先使用 API Token 或受控 JWT
# HTTP 示例：
# Authorization: Bearer apt_xxx 或 Bearer <jwt>
```

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
