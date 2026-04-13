# 小米音箱桥接 (Xiaomi Bridge) 使用说明

## 概述

小米音箱桥接模块将 [open-xiaoai-bridge](https://github.com/coderzc/open-xiaoai-bridge) 的核心能力集成到 miloco_server 中，实现小米音箱与 Miloco AI 对话的无缝对接。

### 功能架构

```
小米音箱 → WebSocket → 音频流 → KWS(唤醒词检测)
                                    ↓
                              VAD(语音活动检测)
                                    ↓
                              ASR(语音识别)
                                    ↓
                           Miloco(大模型对话)
                                    ↓
                              TTS(语音合成)
                                    ↓
                         小米音箱播放回复
```

## 快速开始

### 1. 配置环境变量

复制示例配置并修改：

```bash
cp config/xiaomi_bridge.env.example config/xiaomi_bridge.env
```

编辑 `config/xiaomi_bridge.env`，必填项：

```ini
# 启用桥接
MILOCO_BRIDGE_ENABLED=1

# 豆包 TTS 凭证（二选一）
MILOCO_TTS_ENGINE=doubao
MILOCO_DOUBAO_APP_ID=your_app_id
MILOCO_DOUBAO_ACCESS_KEY=your_access_key
```

### 2. 安装依赖

依赖已在 `pyproject.toml` 中声明：

```bash
# 核心依赖（已包含）
onnxruntime>=1.16.0
numpy>=1.24.0
httpx>=0.25.0
websockets>=12.0

# 可选：Sherpa-ONNX（用于 KWS/ASR）
pip install sherpa-onnx

# 可选：Silero VAD ONNX 模型
# 下载 silero_vad.onnx 到 models/ 目录
```

### 3. 启动服务

```bash
# 加载环境变量
export $(cat config/xiaomi_bridge.env | grep -v '^#' | xargs)

# 启动 miloco_server
python -m miloco_server.main
```

桥接模块随 miloco_server 自动初始化。

### 4. 小米音箱端配置

在小米音箱上安装 open-xiaoai-bridge 客户端，配置 WebSocket 地址指向 miloco_server：

```bash
# 小米音箱端配置
XIAOAI_WS_URL=ws://<server_ip>:4399/ws/audio?client_id=xiaomi_speaker
```

## 配置详解

### VAD (语音活动检测)

```ini
# 检测阈值 (0-1)，越小越灵敏
MILOCO_VAD_THRESHOLD=0.10

# 最小语音时长 (ms)，短于此值不触发
MILOCO_VAD_MIN_SPEECH=250

# 最小静默时长 (ms)，用于判定语音结束
MILOCO_VAD_MIN_SILENCE=500

# Silero VAD ONNX 模型路径（可选，不配置则使用能量检测）
MILOCO_VAD_MODEL_PATH=/path/to/silero_vad.onnx
```

### KWS (关键词检测)

```ini
# 唤醒词（逗号分隔）
MILOCO_WAKEUP_KEYWORDS=小米同学

# 置信度加成 (越高越难误触发)
MILOCO_KWS_SCORE=2.0

# 检测阈值
MILOCO_KWS_THRESHOLD=0.2

# Sherpa-ONNX KWS 模型目录
MILOCO_KWS_MODEL_DIR=/path/to/sherpa-onnx-kws
```

### ASR (语音识别)

```ini
# 模型后端: sense_voice / paraformer / fire_red_asr
MILOCO_ASR_MODEL=sense_voice

# INT8 量化 (加速推理)
MILOCO_ASR_INT8=1

# 模型目录
MILOCO_ASR_MODEL_DIR=/path/to/sense-voice

# 推理线程数
MILOCO_ASR_THREADS=2
```

### TTS (语音合成)

```ini
# 引擎: doubao / xiaoai
MILOCO_TTS_ENGINE=doubao

# 豆包凭证
MILOCO_DOUBAO_APP_ID=
MILOCO_DOUBAO_ACCESS_KEY=

# 音色
MILOCO_DOUBAO_VOICE=zh_female_vv_uranus_bigtts

# 音频格式: pcm / mp3
MILOCO_TTS_FORMAT=pcm

# 流式播放
MILOCO_TTS_STREAM=1

# 语速 (0.5-2.0)
MILOCO_TTS_SPEED=1.0
```

### 对话控制

```ini
# 退出关键词（逗号分隔）
MILOCO_EXIT_KEYWORDS=退出,结束对话,停止

# 无语音超时 (秒)
MILOCO_WAKEUP_TIMEOUT=20
```

### 音频

```ini
# 采样率
MILOCO_SAMPLE_RATE=16000

# 输入增益 (1.0=不处理)
MILOCO_AUDIO_GAIN=1.0

# WebSocket 端口
MILOCO_WS_PORT=4399
MILOCO_WS_HOST=0.0.0.0
```

## API 接口

### 状态查询

```
GET /api/xiaomi-bridge/status
```

响应：
```json
{
  "enabled": true,
  "active": false,
  "state": "idle"
}
```

### 手动唤醒

```
POST /api/xiaomi-bridge/wakeup
Body: {"text": "小米同学"}
```

### 文本对话

```
POST /api/xiaomi-bridge/text
Body: {"text": "今天天气怎么样"}
```

### 停止对话

```
POST /api/xiaomi-bridge/stop
```

### 更新配置

```
POST /api/xiaomi-bridge/config
Body: {
  "wakeup_keywords": ["小米同学", "你好小米"],
  "exit_keywords": ["退出", "停止"]
}
```

### WebSocket 音频流

```
ws://<host>:4399/ws/audio?client_id=xiaomi_speaker
```

音频格式：16kHz, 16-bit, Mono PCM

## 对话流程

```
1. 空闲状态：持续监听唤醒词
2. 检测到唤醒词 → 进入 LISTENING 状态
3. VAD 检测到语音开始 → 开始录制
4. VAD 检测到语音结束 → 停止录制
5. ASR 转录音频为文本
6. 检查退出关键词 → 若匹配则返回空闲
7. 将文本发送给 Miloco 大模型
8. 获取回复文本
9. TTS 合成语音并播放
10. 返回步骤 2，继续下一轮对话
```

## 故障排查

### 桥接未启动

检查 `MILOCO_BRIDGE_ENABLED=1` 是否设置。

### 唤醒词不响应

- 确认 KWS 模型目录配置正确
- 检查 `keywords.txt` 文件是否存在
- 尝试调低 `MILOCO_KWS_THRESHOLD`

### ASR 无结果

- 确认模型目录包含 `tokens.txt` 和对应的 `.onnx` 文件
- 检查 `MILOCO_ASR_MODEL` 与模型文件是否匹配

### TTS 无声

- 确认 `MILOCO_DOUBAO_APP_ID` 和 `MILOCO_DOUBAO_ACCESS_KEY` 已配置
- 检查网络连接是否能访问 `openspeech.bytedance.com`

### 查看日志

```bash
# 启用 DEBUG 日志
LOG_LEVEL=debug python -m miloco_server.main
```

## 项目结构

```
miloco_server/xiaomi_bridge/
├── __init__.py          # 模块导出
├── config.py            # 配置数据类
├── vad.py               # VAD 管理器
├── kws.py               # KWS 管理器
├── asr.py               # ASR 管理器
├── conversation.py      # 对话控制器
├── manager.py           # 桥接管理器
└── audio_stream.py      # WebSocket 音频流
```