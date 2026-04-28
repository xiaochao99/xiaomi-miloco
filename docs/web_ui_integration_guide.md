# Web UI 集成 OpenClaw 框架指南

## 概述

本文档说明如何在 Web UI 中集成和使用 OpenClaw 框架。

## 当前架构

```
Web UI (WebSocket)
    │
    ▼
ChatController (ws_query)
    │
    ▼
ChatAgentDispatcher (Actor)
    │
    ├──▶ NlpRequestAgent (ChatAgent) ──▶ LLM + Tools
    │
    └──▶ ActionDescriptionDynamicExecuteAgent ──▶ LLM + Tools
```

## 集成方式

### 方式一：直接使用 EnhancedChatAgent（推荐）

将 `NlpRequestAgent` 继承自 `EnhancedChatAgent` 而不是 `ChatAgent`。

#### 修改步骤

1. **修改 `nlp_request_agent.py`**

```python
# 修改前
from miloco_server.agent.chat_agent import ChatAgent

class NlpRequestAgent(ChatAgent):
    ...
```

```python
# 修改后
from miloco_server.agent import EnhancedChatAgent

class NlpRequestAgent(EnhancedChatAgent):
    ...
```

2. **配置角色选择（可选）**

在 `NlpRequestAgent` 中添加角色选择逻辑：

```python
class NlpRequestAgent(EnhancedChatAgent):
    def _handle_nlp_request(self, payload: Nlp.Request) -> None:
        query = payload.query
        
        # 自动选择角色
        role = auto_select_role(query)
        if role.config.name != self._active_role.config.name:
            self._active_role = role
            # 更新系统提示词
            self._chat_history_messages.update_system_message(
                self._build_enhanced_system_prompt()
            )
        
        # 原有逻辑...
        self._send_instruction(Internal.Dispatcher(current_query=query, need_storage_history=True))
        mcp_list = payload.mcp_list
        self._set_tools_meta(mcp_list)
        
        # ...
```

### 方式二：通过 ChatAgentDispatcher 配置

在 `ChatAgentDispatcher` 中根据配置决定使用哪个 Agent。

#### 修改 `chat_agent_dispatcher.py`

```python
from miloco_server.agent import EnhancedChatAgent, ChatAgent
from miloco_server.config import CHAT_CONFIG

class ChatAgentDispatcher(Actor):
    def _handle_event(self, event: Event) -> None:
        # ...
        if event.judge_type("Nlp", "Request"):
            # 根据配置选择 Agent
            use_openclaw = CHAT_CONFIG.get("use_openclaw", True)
            
            if use_openclaw:
                from miloco_server.agent.nlp_request_agent_enhanced import NlpRequestAgentEnhanced
                agent_class = NlpRequestAgentEnhanced
            else:
                from miloco_server.agent.nlp_request_agent import NlpRequestAgent
                agent_class = NlpRequestAgent
            
            self._chat_agent = actor_system.createActor(
                lambda: agent_class(...)
            )
```

### 方式三：渐进式迁移（向后兼容）

保留原有 Agent，通过配置开关控制。

#### 1. 创建增强版 NlpRequestAgent

创建 `nlp_request_agent_enhanced.py`：

```python
from miloco_server.agent.nlp_request_agent import NlpRequestAgent
from miloco_server.agent import EnhancedChatAgent

class NlpRequestAgentEnhanced(NlpRequestAgent, EnhancedChatAgent):
    """增强版 NlpRequestAgent，继承两者功能"""
    
    def __init__(self, *args, **kwargs):
        # 初始化 EnhancedChatAgent 的功能
        super().__init__(*args, **kwargs)
    
    def _handle_nlp_request(self, payload: Nlp.Request) -> None:
        # 添加 OpenClaw 特性
        query = payload.query
        
        # 智能工具选择
        from miloco_server.agent import select_tools
        tool_selections = select_tools(query, top_k=5)
        logger.info("Tool selections: %s", [s.tool_name for s in tool_selections])
        
        # 调用父类方法
        super()._handle_nlp_request(payload)
```

#### 2. 配置开关

在 `config/chat_config.yaml` 中添加：

```yaml
# OpenClaw 框架配置
use_openclaw: true
openclaw:
  default_role: "smart_home_assistant"
  enable_auto_role_selection: true
  enable_intelligent_tool_selection: true
  enable_adaptive_learning: true
```

## 使用方式

### 对于用户

用户**不需要**做任何改变，直接通过 AI 对话界面进行对话即可。

OpenClaw 框架会在后台自动：
1. 根据查询内容自动选择最适合的角色
2. 智能选择需要使用的工具
3. 生成优化的提示词
4. 处理错误和异常
5. 学习和优化响应

### 对于开发者

#### 查看统计信息

```python
from miloco_server.agent import get_stats

# 获取系统统计
stats = get_stats()
print(stats)
```

#### 切换角色

```python
from miloco_server.agent import openclaw

# 切换到特定角色
role = openclaw.switch_role("security_guardian")
```

#### 查看学习数据

```python
# 获取学习统计
learning_stats = openclaw.get_learning_stats()

# 获取优化建议
suggestions = openclaw.get_optimization_suggestions()
```

## 配置示例

### 完整配置 (`config/openclaw_config.yaml`)

```yaml
# 是否启用 OpenClaw 框架
use_openclaw: true

# 角色配置
roles:
  default_role: "smart_home_assistant"
  
# 工具选择器配置
tool_selector:
  default_strategy: "HYBRID"
  enable_adaptive: true

# 上下文管理器配置
context_manager:
  max_contexts: 100
  context_ttl_seconds: 3600

# 自适应学习器配置
adaptive_learner:
  learning_rate: 0.1
  enable_auto_optimization: true

# 错误处理器配置
error_handler:
  max_retries: 3
  enable_graceful_degradation: true
```

## 监控和调试

### 日志输出

框架会自动输出详细的日志信息：

```
[INFO] Auto-selected role: 智能家居助手
[INFO] Tool selections: ['create_rule', 'cached_get_device_state']
[INFO] Context state: THINKING -> EXECUTING -> COMPLETED
[INFO] Learning record added: intent=turn_on, success=True
```

### 性能监控

```python
# 获取工具性能统计
tool_stats = openclaw._tool_selector.get_tool_stats()

# 获取错误统计
error_stats = openclaw.get_error_stats()

# 获取上下文统计
context_stats = openclaw.get_context_manager().get_context_stats()
```

## 故障排除

### 常见问题

#### 1. 角色切换不生效
**解决**: 检查是否正确更新了系统提示词

#### 2. 工具选择不准确
**解决**: 
- 检查关键词映射配置
- 增加训练数据
- 调整策略权重

#### 3. 响应变慢
**解决**:
- 启用工具选择缓存
- 调整上下文窗口大小
- 优化模板渲染

## 最佳实践

1. **渐进式启用**: 先在小范围测试，再全面部署
2. **监控性能**: 定期检查统计信息
3. **持续学习**: 定期导出和分析学习数据
4. **用户反馈**: 收集用户满意度数据

## 总结

集成 OpenClaw 框架后，Web UI 的用户体验将得到显著提升：

- ✅ **更智能的响应** - 根据场景自动选择最适合的角色
- ✅ **更精准的工具调用** - 智能选择最相关的工具
- ✅ **更好的多轮对话** - 完整的上下文管理
- ✅ **更强的容错能力** - 多层次错误恢复
- ✅ **持续优化** - 从交互中学习和改进

用户只需正常使用 AI 对话功能，即可享受 OpenClaw 带来的智能化增强。
