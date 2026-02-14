# 实时目标检测模块 (Real-time Object Detection)

基于轻量级YOLO模型的本地实时目标检测系统，无需依赖大模型即可检测画面中的人、猫、狗。

## 功能特性

- **轻量级检测**: 使用YOLOv8-nano模型，单帧推理时间约10-30ms
- **本地运行**: 无需联网，保护隐私
- **实时流处理**: 支持多摄像头并发检测
- **目标追踪**: 跨帧跟踪同一目标
- **低资源占用**: CPU模式也可流畅运行

## 支持的检测目标

| 类别 | COCO ID | 说明 |
|------|---------|------|
| person | 0 | 人 |
| cat | 15 | 猫 |
| dog | 16 | 狗 |

## 安装依赖

```bash
# 安装检测模块依赖
pip install -e ".[detection]"

# 或者手动安装
pip install onnxruntime opencv-python-headless numpy
```

## 配置说明

### 检测参数配置

在 `config/server_config.yaml` 中添加检测配置:

```yaml
# 实时检测配置
detection:
  enabled: true
  # 全局检测配置
  confidence_threshold: 0.5    # 置信度阈值 (0.0-1.0)
  iou_threshold: 0.45          # NMS IoU阈值
  process_fps: 5               # 处理帧率 (降低可减少CPU占用)
  min_detection_interval: 0.5  # 最小检测间隔(秒)
  enable_tracking: true        # 启用目标追踪
  
  # 按摄像头配置
  cameras:
    camera_did_1:
      process_fps: 3
      confidence_threshold: 0.6
    camera_did_2:
      process_fps: 10
```

## API 使用

### 1. 启动摄像头检测

```bash
POST /api/detection/start
Content-Type: application/json

{
  "camera_id": "camera_did_1",
  "config": {
    "process_fps": 5,
    "confidence_threshold": 0.5
  }
}
```

### 2. 停止摄像头检测

```bash
POST /api/detection/stop/{camera_id}
```

### 3. 获取检测状态

```bash
GET /api/detection/status
```

返回:
```json
{
  "active": true,
  "detector_info": {
    "initialized": true,
    "device": "cuda",
    "input_size": [640, 640]
  },
  "active_cameras": ["camera_did_1"],
  "stats": {...}
}
```

### 4. 获取所有摄像头检测状态

```bash
GET /api/detection/cameras
```

### 5. 获取指定摄像头统计

```bash
GET /api/detection/stats/{camera_id}
```

## WebSocket 实时推送

### 全局事件流 (所有摄像头)

```javascript
const ws = new WebSocket('wss://localhost:8000/api/detection/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('检测事件:', data);
  // {
  //   type: 'detection',
  //   camera_id: 'camera_1',
  //   timestamp: 1704067200.123,
  //   detections: [
  //     { class_name: 'person', confidence: 0.92, bbox: [0.1, 0.2, 0.3, 0.4] }
  //   ],
  //   tracked_objects: [...]
  // }
};

// 发送ping保活
ws.send(JSON.stringify({ type: 'ping' }));
```

### 指定摄像头事件流

```javascript
const ws = new WebSocket('wss://localhost:8000/api/detection/ws/camera_1');
```

### WebSocket 消息类型

#### 服务器发送

| 类型 | 说明 |
|------|------|
| `detection` | 检测到目标 |
| `status` | 状态信息 |
| `pong` | ping响应 |

#### 客户端发送

| 类型 | 说明 |
|------|------|
| `ping` | 心跳检测 |
| `get_status` | 获取状态 |
| `subscribe_camera` | 订阅指定摄像头 |
| `unsubscribe_camera` | 取消订阅 |

## 性能优化建议

1. **降低处理帧率**: 将 `process_fps` 设置为 3-5 FPS 可大幅降低CPU占用
2. **调整置信度阈值**: 提高阈值可减少误报但可能漏检
3. **使用GPU**: 安装 `onnxruntime-gpu` 启用CUDA加速
4. **分辨率调整**: 检测会自动将图像缩放到 640x640

## 模型信息

- 模型: YOLOv8-nano (YOLOv8n)
- 输入尺寸: 640x640
- 格式: ONNX
- 大小: ~6MB
- 自动下载: 首次启动时自动从GitHub下载

## 架构说明

```
Camera Stream → Frame Queue → Object Detector → Event Handler → WebSocket
                     ↓
               Stream Processor (rate limiting, tracking)
```

## 注意事项

1. 模型首次启动时会自动下载，需要网络连接
2. 检测服务依赖摄像头流先启动
3. CPU模式下建议 process_fps <= 5
4. 摄像头DID需要与实际注册的摄像头一致
