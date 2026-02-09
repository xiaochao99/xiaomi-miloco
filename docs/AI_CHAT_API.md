# AI Chat REST API 文档

## 概述

AI Chat REST API 提供了一个简单的HTTP接口，让第三方平台可以发送文字命令到AI对话系统，并接收AI的处理结果。

**核心功能**:
- **AI对话**: 支持自然语言交互，控制智能家居设备
- **视觉分析**: 调用摄像头进行实时画面分析（支持自动摄像头匹配）
- **米家集成**: 发送通知、获取设备列表、执行场景等
- **双模式输出**: 支持同步返回和流式输出（SSE）

## 基础信息

- **Base URL**: `https://127.0.0.1:28443/api`
- **认证方式**: JWT Token 或 API Token (Bearer)
- **Content-Type**: `application/json`

## 视觉分析说明

### 智能摄像头匹配

当 `enable_vision=true` 时，系统会自动进行摄像头匹配：

1. **自动位置匹配**: 从用户查询中提取位置关键词（如"客厅"、"卧室"），自动匹配对应摄像头
2. **手动指定**: 通过 `camera_id` 参数指定特定摄像头
3. ** fallback **: 如果未匹配到位置且未指定camera_id，使用第一个在线摄像头

** 支持的位置关键词 **:
- 客厅、卧室、厨房、阳台、门口、书房、卫生间、花园

### 视觉分析流程

```
用户发送请求 → 提取位置关键词 → 匹配摄像头 → 获取实时画面 → AI视觉模型分析 → 返回分析结果
```

## API端点

### POST /ai/chat

AI对话接口（同步返回），支持文字对话和摄像头视觉分析。

**响应格式**: JSON（完整响应）

### POST /ai/chat/stream

AI对话接口（流式输出），使用SSE（Server-Sent Events）实现实时响应。

**响应格式**: SSE事件流

**适用场景**:
- 需要实时显示AI回复的聊天界面
- 长时间处理的任务，避免HTTP超时
- 提升用户体验，减少等待感

#### 请求参数

```json
{
    "message": "你好，请介绍一下你的功能",
    "enable_vision": false,
    "camera_id": null,
    "context_messages": null
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户输入的文字命令 |
| enable_vision | boolean | 否 | 是否启用摄像头视觉分析，默认false |
| camera_id | string | 否 | 摄像头设备ID（启用视觉分析时需要） |
| context_messages | array | 否 | 对话上下文，格式: `[{role: 'user'/'assistant', content: '...'}]` |

#### 响应参数

```json
{
    "request_id": "req_2c3155a12345",
    "response": "我是小米智能家居AI助手，可以帮助您控制设备、发送通知、查看摄像头等。",
    "vision_analysis": null,
    "executed_actions": ["ai_chat_processing"],
    "processing_time": 1.23
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| request_id | string | 请求唯一标识 |
| response | string | AI回复内容 |
| vision_analysis | string | 摄像头画面分析结果（如果启用） |
| executed_actions | array | 执行的动作列表 |
| processing_time | float | 处理耗时（秒） |

## 流式输出说明

### SSE事件类型

流式接口使用Server-Sent Events (SSE) 格式返回数据：

#### 1. metadata事件
初始元数据，包含请求ID和时间戳

```
event: metadata
data: {"request_id": "req_xxx", "timestamp": 1234567890}
```

#### 2. vision_analysis事件
视觉分析结果（如果启用）

```
event: vision_analysis
data: {"vision_analysis": "检测到客厅场景..."}
```

#### 3. chunk事件
AI回复的内容块

```
event: chunk
data: {"content": "我是小米", "finish_reason": null}
```

#### 4. complete事件
处理完成，包含完整响应

```
event: complete
data: {
  "request_id": "req_xxx",
  "response": "我是小米智能家居AI助手...",
  "vision_analysis": null,
  "executed_actions": ["ai_chat_processing"],
  "processing_time": 1.23
}
```

#### 5. error事件
处理错误

```
event: error
data: {"error": "处理失败: 错误信息"}
```

### 流式输出客户端示例

#### JavaScript (浏览器)

```javascript
async function streamAIChat(message, token) {
  const response = await fetch('https://127.0.0.1:28443/api/ai/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ message: message })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n\n');

    for (const line of lines) {
      if (line.startsWith('event: chunk')) {
        const dataLine = lines[lines.indexOf(line) + 1];
        if (dataLine && dataLine.startsWith('data: ')) {
          const data = JSON.parse(dataLine.slice(6));
          console.log('AI回复:', data.content);
          // 实时显示到界面
          document.getElementById('response').textContent += data.content;
        }
      } else if (line.startsWith('event: complete')) {
        console.log('处理完成');
      } else if (line.startsWith('event: error')) {
        const dataLine = lines[lines.indexOf(line) + 1];
        if (dataLine && dataLine.startsWith('data: ')) {
          const data = JSON.parse(dataLine.slice(6));
          console.error('错误:', data.error);
        }
      }
    }
  }
}
```

#### Python

```python
import requests
import json

def stream_ai_chat(message, token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    payload = {"message": message}
    
    response = requests.post(
        'https://127.0.0.1:28443/api/ai/chat/stream',
        headers=headers,
        json=payload,
        stream=True,
        verify=False
    )
    
    full_response = ""
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('event: chunk'):
                # 读取下一行的data
                continue
            elif line_str.startswith('data: '):
                data = json.loads(line_str[6:])
                if 'content' in data:
                    content = data['content']
                    full_response += content
                    print(content, end='', flush=True)
            elif line_str.startswith('event: complete'):
                print('\n处理完成')
                break
            elif line_str.startswith('event: error'):
                print(f'\n错误: {data.get("error", "未知错误")}')
                break
    
    return full_response
```

## 使用示例

### 1. 基本对话

**请求**:
```bash
curl -X POST https://127.0.0.1:28443/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "你好，请介绍一下你的功能"
  }'
```

**响应**:
```json
{
    "request_id": "req_abc123",
    "response": "我是小米智能家居AI助手，可以帮助您控制设备、发送通知、查看摄像头等。",
    "vision_analysis": null,
    "executed_actions": ["ai_chat_processing"],
    "processing_time": 0.85
}
```

### 2. 发送米家通知

**请求**:
```bash
curl -X POST https://127.0.0.1:28443/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "发送通知: 我到家了"
  }'
```

**响应**:
```json
{
    "request_id": "req_def456",
    "response": "已发送米家通知: 我到家了",
    "vision_analysis": null,
    "executed_actions": ["ai_chat_processing"],
    "processing_time": 1.12
}
```

### 3. 获取设备列表

**请求**:
```bash
curl -X POST https://127.0.0.1:28443/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "获取我的设备列表"
  }'
```

**响应**:
```json
{
    "request_id": "req_ghi789",
    "response": "找到以下设备：\n1. 客厅空调\n2. 卧室灯\n3. 智能门锁\n4. 客厅摄像头",
    "vision_analysis": null,
    "executed_actions": ["ai_chat_processing"],
    "processing_time": 2.34
}
```

### 4. 启用摄像头视觉分析

**请求**:
```bash
curl -X POST https://127.0.0.1:28443/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "查看摄像头，告诉我看到了什么",
    "enable_vision": true,
    "camera_id": "camera_001"
  }'
```

**响应**:
```json
{
    "request_id": "req_jkl012",
    "response": "我看到客厅里有沙发、茶几和电视，目前没有发现异常情况。",
    "vision_analysis": "检测到客厅场景，包含沙发、茶几、电视等家具，环境整洁。",
    "executed_actions": ["analyze_camera_image", "ai_chat_processing"],
    "processing_time": 3.45
}
```

### 5. 带上下文的对话

**请求**:
```bash
curl -X POST https://127.0.0.1:28443/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "好的，请帮我打开",
    "context_messages": [
      {"role": "user", "content": "我想打开客厅的灯"},
      {"role": "assistant", "content": "请问您想打开哪个灯？客厅有主灯和氛围灯。"}
    ]
  }'
```

### 6. 流式输出

**请求**:
```bash
curl -X POST https://127.0.0.1:28443/api/ai/chat/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "请详细介绍你的所有功能"
  }'
```

**响应**（SSE流式）：
```
event: metadata
data: {"request_id": "req_abc123", "timestamp": 1234567890}

event: chunk
data: {"content": "我是", "finish_reason": null}

event: chunk
data: {"content": "小米智能家居", "finish_reason": null}

event: chunk
data: {"content": "AI助手", "finish_reason": null}

event: complete
data: {
  "request_id": "req_abc123",
  "response": "我是小米智能家居AI助手...",
  "vision_analysis": null,
  "executed_actions": ["ai_chat_processing"],
  "processing_time": 1.56
}
```

## 认证方式

### 方式1：JWT Token（Web登录后获取）

```bash
-H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 方式2：API Token（长期有效）

```bash
-H "Authorization: Bearer apt_xxxxxxxxxxxxxxxxxxxx"
```

API Token可以在WebUI的设置页面中生成和管理。

## 错误处理

### 认证失败

**状态码**: 401 Unauthorized
```json
{
    "detail": "Invalid or expired API token"
}
```

### 处理错误

**状态码**: 500 Internal Server Error
```json
{
    "detail": "处理失败: <错误信息>"
}
```

## 速率限制

- 每个用户每分钟最多100次请求
- 超过限制返回 `429 Too Many Requests`

## 最佳实践

1. **使用API Token**: 对于第三方平台集成，建议使用长期有效的API Token
2. **错误处理**: 实现重试机制，处理网络超时和服务器错误
3. **上下文管理**: 对于多轮对话，使用 `context_messages` 传递历史消息
4. **视觉分析**: 仅在需要时启用 `enable_vision`，以减少处理时间和资源消耗

## 测试脚本

项目提供了测试脚本 `test_ai_chat_api.py`：

```bash
# 使用JWT Token测试
python test_ai_chat_api.py https://127.0.0.1:28443 eyJhbGciOiJ...

# 使用API Token测试
python test_ai_chat_api.py https://127.0.0.1:28443 apt_xxxxx
```

## 相关文档

- [OpenAI Compatible API](OPENAI_API.md) - OpenAI兼容接口文档
- [API Token Management](API_TOKEN.md) - API Token管理说明

## 支持与反馈

如有问题或建议，请通过以下方式联系：
- 提交Issue: [项目Issue页面](https://gitea.hypernas.cn/xiaochao/xiaomi-miloco/issues)
- 文档更新: [编辑本文档](https://gitea.hypernas.cn/xiaochao/xiaomi-miloco/src/branch/main/docs/AI_CHAT_API.md)
