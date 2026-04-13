# Xiaomi Speaker Bridge Integration

小米音箱桥接模块 - 将 open-xiaoai-bridge 的能力集成到 miloco_server 中。

## 功能特性

### 1. 小爱音箱播放 Miloco 回复语音

- **TTS 服务**: 支持豆包 TTS 和小爱原生 TTS
- **流式播放**: 支持实时语音合成和播放
- **API 集成**: 通过 `/api/xiaomi-bridge/` 接口控制播放

### 2. 自定义唤醒词进入对话模式

- **KWS (关键词唤醒)**: 支持自定义唤醒词（默认："小米同学"）
- **VAD (语音活动检测)**: 自动检测语音开始和结束
- **ASR (语音识别)**: 将语音转为文字（支持 sherpa-onnx 和 Whisper）
- **连续对话**: 唤醒后自动进入对话循环

### 3. 完整的音频处理链

- **GlobalStream**: 多路音频输入广播
- **Silero VAD**: ONNX 语音活动检测
- **Sherpa ASR**: SenseVoice 离线语音识别
- **Doubao TTS**: 火山引擎语音合成

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     Miloco Server                        │
├─────────────────────────────────────────────────────────┤
│  Xiaomi Bridge Module                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │   KWS    │  │   VAD    │  │   ASR    │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                    │
│       └──────────────┼──────────────┘                    │
│                      ▼                                   │
│              ┌──────────────┐                            │
│              │ Conversation │                            │
│              │  Controller  │                            │
│              └──────┬───────┘                            │
│                     ▼                                   │
│              ┌──────────────┐                            │
│              │ Miloco Model │                            │
│              └──────┬───────┘                            │
│                     ▼                                   │
│              ┌──────────────┐                            │
│              │  TTS Service │                            │
│              └──────────────┘                            │
└─────────────────────────────────────────────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │   Xiaomi Speaker     │
          │  (via WebSocket)     │
          └──────────────────────┘
```

## 快速开始

### 1. 环境变量配置

```bash
# 启用桥接
MILOCO_BRIDGE_ENABLED=1

# 唤醒词配置
MILOCO_WAKEUP_KEYWORDS=小米同学,你好小米

# 退出关键词
MILOCO_EXIT_KEYWORDS=退出,结束对话,停止

# TTS 配置（豆包）
MILOCO_TTS_ENGINE=doubao
MILOCO_DOUBAO_APP_ID=your_app_id
MILOCO_DOUBAO_ACCESS_TOKEN=your_token

# 模型路径（可选）
MILOCO_KWS_MODEL_PATH=/path/to/kws/models
MILOCO_ASR_MODEL_PATH=/path/to/asr/models
```

### 2. API 接口

#### 获取桥接状态
```http
GET /api/xiaomi-bridge/status
```

响应:
```json
{
  "enabled": true,
  "active": false,
  "state": "idle"
}
```

#### 触发唤醒
```http
POST /api/xiaomi-bridge/wakeup
Content-Type: application/json

{
  "text": "你好小米"
}
```

#### 发送文本处理
```http
POST /api/xiaomi-bridge/text
Content-Type: application/json

{
  "text": "今天天气怎么样"
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
  "wakeup_keywords": ["小米同学", "你好小爱"],
  "exit_keywords": ["退出", "停止"],
  "tts_engine": "doubao"
}
```

### 3. Python 代码调用

```python
from miloco_server.xiaomi_bridge.manager import get_bridge_manager, init_bridge
from miloco_server.xiaomi_bridge.config import BridgeConfig

# 初始化
config = BridgeConfig.from_env()
manager = await init_bridge(config)

# 触发唤醒
await manager.conversation_controller.on_wakeup("小米同学")

# 播放语音
await manager.speak("你好，我是小米助手")

# 处理文本
response = await manager.conversation_controller.process_text("今天天气怎么样")
```

## 组件说明

### BridgeConfig

桥接配置类，支持从环境变量加载。

```python
@dataclass
class BridgeConfig:
    enabled: bool = False
    wakeup_keywords: List[str] = ["小米同学"]
    exit_keywords: List[str] = ["退出", "结束对话", "停止"]
    tts_engine: str = "doubao"  # "doubao" or "xiaoai"
    doubao_app_id: str = ""
    doubao_access_token: str = ""
    sample_rate: int = 16000
    vad_threshold: float = 0.5
```

### MilocoConversationController

对话控制器，管理连续对话流程。

状态机:
- `IDLE`: 空闲状态
- `LISTENING`: 监听语音
- `PROCESSING`: 处理中（调用 Miloco）
- `SPEAKING`: 播放 TTS

### AudioProcessor

音频处理器，集成 VAD 和 ASR。

```python
processor = AudioProcessor(sample_rate=16000)
await processor.initialize(vad_threshold=0.5)

# 设置语音结束回调
processor.set_speech_end_callback(on_speech_end)

# 处理音频帧
await processor.process_audio_chunk(audio_data)
```

### TTSService

TTS 服务，支持豆包和小爱两种引擎。

```python
tts = TTSService.from_env()
await tts.initialize()

# 合成语音
audio = await tts.synthesize("你好")

# 直接播放
await tts.speak("你好，我是小米助手")
```

## Docker 部署

### docker-compose.yaml 配置

```yaml
services:
  miloco-server:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    environment:
      - MILOCO_BRIDGE_ENABLED=1
      - MILOCO_WAKEUP_KEYWORDS=小米同学
      - MILOCO_TTS_ENGINE=doubao
      - MILOCO_DOUBAO_APP_ID=${DOUBAO_APP_ID}
      - MILOCO_DOUBAO_ACCESS_TOKEN=${DOUBAO_TOKEN}
    ports:
      - "8000:8000"
```

### 构建镜像

```bash
cd docker
docker compose build
```

## 依赖项

### Python 包
- fastapi >= 0.115.3
- uvicorn >= 0.24.0
- httpx >= 0.25.0
- numpy >= 1.24.0
- onnxruntime >= 1.16.0

### 可选依赖
- sherpa-onnx: KWS 和 ASR
- torch: Silero VAD
- whisper: 备用 ASR

### 模型文件
- KWS 模型: `core/models/kws/`
- VAD 模型: Silero ONNX（自动下载）
- ASR 模型: sherpa-onnx SenseVoice

## 与 open-xiaoai-bridge 的对应关系

| open-xiaoai-bridge | miloco_server xiaomi_bridge |
|-------------------|----------------------------|
| `core/xiaoai.py` | `xiaomi_bridge/manager.py` |
| `core/xiaozhi.py` | `conversation.py` |
| `core/openclaw.py` | 通过 Miloco API 调用 |
| `core/openclaw_conversation.py` | `conversation.py` |
| `services/audio/vad/silero.py` | `audio_processor.py` |
| `services/audio/kws/sherpa.py` | `kws.py` |
| `services/audio/asr/sherpa.py` | `asr.py` |
| `services/tts/doubao.py` | `tts_service.py` |

## 开发指南

### 添加新的 TTS 引擎

1. 在 `tts_service.py` 中创建新的 TTS 客户端类
2. 实现 `synthesize(text) -> bytes` 方法
3. 在 `TTSService.initialize()` 中注册新引擎

### 添加新的 ASR 后端

1. 在 `asr.py` 中创建新的 ASR 客户端类
2. 实现 `transcribe(audio_data, sample_rate) -> str` 方法
3. 在 `BridgeManager.initialize()` 中配置使用

### 自定义唤醒流程

1. 继承 `MilocoConversationController`
2. 重写 `process_text()` 方法
3. 添加自定义的唤醒逻辑

## 故障排除

### 问题：桥接未启用

检查环境变量：
```bash
echo $MILOCO_BRIDGE_ENABLED
```

### 问题：TTS 播放失败

检查 TTS 配置：
```bash
curl -X POST http://localhost:8000/api/xiaomi-bridge/text \
  -H "Content-Type: application/json" \
  -d '{"text": "测试播放"}'
```

### 问题：唤醒词不工作

检查日志输出，确认 KWS 是否初始化：
```bash
grep "KWS initialized" /var/log/miloco.log
```

## 参考资料

- [open-xiaoai-bridge](https://github.com/coderzc/open-xiaoai-bridge)
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [Doubao TTS API](https://www.volcengine.com/docs/6561/79817)