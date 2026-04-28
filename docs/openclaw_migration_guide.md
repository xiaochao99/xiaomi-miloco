# OpenClaw 框架迁移指南

## 概述

本文档指导如何将现有的 ChatAgent 迁移到使用 OpenClaw 框架的 EnhancedChatAgent。

## 主要改进

### 1. 角色管理 (Role Management)
- **旧版**: 固定的系统提示词
- **新版**: 动态角色系统，支持多种预定义角色和自定义角色
- **优势**: 根据查询自动选择最适合的角色，提升响应质量

### 2. 提示词模板系统 (Prompt Template System)
- **旧版**: 静态 YAML 配置
- **新版**: 动态模板引擎，支持变量替换、条件渲染和循环
- **优势**: 更灵活的提示词生成，上下文感知

### 3. 智能工具选择 (Intelligent Tool Selection)
- **旧版**: 固定工具列表
- **新版**: 基于意图、语义和历史表现的智能选择
- **优势**: 更精准的工具调用，减少无效调用

### 4. 上下文管理 (Context Management)
- **旧版**: 简单的消息历史
- **新版**: 完整的对话状态追踪，实体提取
- **优势**: 更好的多轮对话支持

### 5. 自适应学习 (Adaptive Learning)
- **旧版**: 无学习机制
- **新版**: 持续学习用户偏好和工具效果
- **优势**: 系统性能随使用提升

### 6. 错误处理 (Error Handling)
- **旧版**: 简单的 try-catch
- **新版**: 多层次恢复策略
- **优势**: 更好的容错性和用户体验

## 迁移步骤

### 步骤 1: 更新导入语句

**旧代码**:
```python
from miloco_server.agent.chat_agent import ChatAgent
```

**新代码**:
```python
# 继续使用旧版（向后兼容）
from miloco_server.agent.chat_agent import ChatAgent

# 或使用新版
from miloco_server.agent import EnhancedChatAgent

# 或使用集成接口
from miloco_server.agent import openclaw
```

### 步骤 2: 初始化 OpenClaw 组件

**在应用启动时**:
```python
from miloco_server.agent import openclaw

# 自动初始化所有组件
# 角色管理器、工具选择器、模板引擎等

# 可选：加载自定义配置
openclaw.switch_role("smart_home_assistant")  # 设置默认角色
```

### 步骤 3: 更新 Agent 创建

**旧代码**:
```python
from miloco_server.agent.chat_agent import ChatAgent

agent = ChatAgent(
    request_id="req_001",
    out_actor_address=address,
    chat_history_messages=history,
)
```

**新代码**:
```python
from miloco_server.agent import EnhancedChatAgent

agent = EnhancedChatAgent(
    request_id="req_001",
    out_actor_address=address,
    chat_history_messages=history,
    role_name="smart_home_assistant",  # 可选：指定角色
)
```

### 步骤 4: 使用智能工具选择

**旧代码**:
```python
# 直接使用所有工具
self._set_tools_meta(mcp_list)
```

**新代码**:
```python
# 使用智能工具选择
from miloco_server.agent import select_tools

# 在 EnhancedChatAgent 中自动完成
# 或手动使用
tool_selections = select_tools(query, top_k=5)
recommended_tools = [s.tool_name for s in tool_selections]
```

### 步骤 5: 添加错误处理

**旧代码**:
```python
try:
    result = await self._execute_step(step)
except Exception as e:
    logger.error(f"Error: {e}")
    raise
```

**新代码**:
```python
# 在 EnhancedChatAgent 中自动完成
# 或手动使用
from miloco_server.agent import openclaw

try:
    result = await self._execute_step(step)
except Exception as e:
    recovery_result = await openclaw.handle_error(
        e,
        context={"step": step, "request_id": self._request_id},
        recovery_context={
            "original_func": self._execute_step,
            "args": [step],
        }
    )
    if recovery_result.get("success"):
        return recovery_result.get("result")
    raise
```

### 步骤 6: 记录学习数据

**旧代码**:
```python
# 无学习机制
```

**新代码**:
```python
from miloco_server.agent import LearningRecord

# 在 EnhancedChatAgent 中自动完成
# 或手动使用
record = LearningRecord(
    session_id=session_id,
    query=query,
    intent=intent,
    selected_tools=tools,
    success=success,
    user_satisfaction=0.9,
    response_time=0.5,
)
openclaw.record_interaction(record)
```

## 配置迁移

### 角色配置

**旧配置** (config/prompt_config.yaml):
```yaml
prompts:
  chat:
    chinese: |
      # 角色与目标
      你是一个高度智能的AI代理...
```

**新配置** (config/openclaw_config.yaml):
```yaml
roles:
  definitions:
    smart_home_assistant:
      name: "智能家居助手"
      description: "专业的智能家居管理助手"
      capabilities:
        - CHAT
        - DEVICE_CONTROL
        - SCENE_MANAGEMENT
      preferred_tools:
        - create_rule
        - vision_understand
```

### 提示词模板配置

**新配置**:
```yaml
prompt_templates:
  defaults:
    system_base:
      section: "system"
      priority: 100
      content: |
        # 角色与目标
        你是一个高度智能的AI代理...
        当前时间: {{current_time}}
```

## 代码示例

### 完整迁移示例

**旧版实现**:
```python
class MyChatAgent(ChatAgent):
    def _parse_and_handle_event(self, event: Event) -> None:
        if event.judge_type("Nlp", "Request"):
            payload = Nlp.Request(**json.loads(event.payload))
            self._handle_nlp_request(payload)
    
    def _handle_nlp_request(self, payload: Nlp.Request) -> None:
        query = payload.query
        self._set_tools_meta(payload.mcp_list)
        asyncio.create_task(self._run_chat(query))
```

**新版实现**:
```python
from miloco_server.agent import EnhancedChatAgent, auto_select_role, select_tools

class MyEnhancedAgent(EnhancedChatAgent):
    def _parse_and_handle_event(self, event: Event) -> None:
        if event.judge_type("Nlp", "Request"):
            payload = Nlp.Request(**json.loads(event.payload))
            self._handle_nlp_request(payload)
    
    def _handle_nlp_request(self, payload: Nlp.Request) -> None:
        query = payload.query
        
        # 自动选择角色
        role = auto_select_role(query)
        if role.config.name != self._active_role.config.name:
            self._active_role = role
            # 重新生成系统提示词
            self._chat_history_messages.update_system_message(
                self._build_enhanced_system_prompt()
            )
        
        # 智能工具选择
        tool_selections = select_tools(query, top_k=5)
        
        # 设置工具（会自动过滤）
        self._set_tools_meta(payload.mcp_list)
        
        # 运行聊天
        asyncio.create_task(self._run_chat(query))
```

## 性能优化建议

### 1. 角色选择优化
```python
# 缓存角色选择结果
_role_cache = {}

def get_cached_role(query: str) -> Role:
    # 使用查询意图作为缓存键
    intent = extract_intent(query)
    if intent not in _role_cache:
        _role_cache[intent] = auto_select_role(query)
    return _role_cache[intent]
```

### 2. 工具选择缓存
```python
# 缓存常见查询的工具选择
_tool_selection_cache = {}

def get_cached_tools(query: str) -> List[ToolSelection]:
    normalized = normalize_query(query)
    if normalized not in _tool_selection_cache:
        _tool_selection_cache[normalized] = select_tools(query)
    return _tool_selection_cache[normalized]
```

### 3. 上下文管理优化
```python
# 定期清理过期上下文
async def cleanup_contexts():
    while True:
        await asyncio.sleep(3600)  # 每小时清理
        context_manager._cleanup_expired()
```

## 故障排除

### 常见问题

#### 1. 角色切换不生效
**问题**: 切换角色后响应风格没有变化
**解决**: 确保重新生成了系统提示词
```python
self._chat_history_messages.update_system_message(
    self._build_enhanced_system_prompt()
)
```

#### 2. 工具选择不准确
**问题**: 工具选择不符合预期
**解决**: 
- 检查关键词映射配置
- 增加训练数据
- 调整策略权重

#### 3. 内存使用过高
**问题**: 上下文管理器占用太多内存
**解决**:
- 减少 max_contexts
- 降低 context_ttl_seconds
- 启用持久化

## 回滚策略

如果需要回滚到旧版：

1. 保留旧版 ChatAgent 导入
2. 切换回旧版实现
3. 禁用 OpenClaw 组件

```python
# 快速回滚
USE_OPENCLAW = False  # 设置为 False 回滚

if USE_OPENCLAW:
    from miloco_server.agent import EnhancedChatAgent as ChatAgent
else:
    from miloco_server.agent.chat_agent import ChatAgent
```

## 监控和调试

### 查看统计信息
```python
from miloco_server.agent import get_stats

stats = get_stats()
print(f"Roles: {stats['roles']}")
print(f"Contexts: {stats['contexts']}")
print(f"Learning: {stats['learning']}")
print(f"Errors: {stats['errors']}")
```

### 导出学习数据
```python
openclaw._adaptive_learner.export_data("./learning_data.json")
```

### 查看错误历史
```python
error_stats = openclaw.get_error_stats()
print(f"Recent errors: {error_stats['recent_errors']}")
```

## 最佳实践

1. **渐进式迁移**: 先在小范围测试，再全面部署
2. **保留回滚能力**: 维护切换开关
3. **监控性能**: 定期检查统计信息
4. **持续学习**: 定期导出和分析学习数据
5. **用户反馈**: 收集用户满意度数据

## 总结

OpenClaw 框架提供了显著的功能增强：
- ✅ 动态角色管理
- ✅ 智能提示词生成
- ✅ 上下文感知工具选择
- ✅ 自适应学习
- ✅ 健壮的错误处理
- ✅ 完整的上下文管理

迁移过程是渐进的，可以按需启用功能。建议从 EnhancedChatAgent 开始，逐步利用更多高级特性。
