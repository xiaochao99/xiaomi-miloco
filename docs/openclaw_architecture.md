# OpenClaw 框架架构文档

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OpenClaw Framework                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    EnhancedChatAgent (增强聊天代理)                   │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐           │   │
│  │  │ RoleManager │  │TemplateEngine│  │ ContextManager   │           │   │
│  │  │   角色管理   │  │  模板引擎     │  │   上下文管理      │           │   │
│  │  └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘           │   │
│  │         │                │                   │                      │   │
│  │  ┌──────▼────────────────▼───────────────────▼─────────┐            │   │
│  │  │              Core Integration Layer                  │            │   │
│  │  │                 (核心集成层)                         │            │   │
│  │  └──────┬────────────────┬───────────────────┬─────────┘            │   │
│  │         │                │                   │                      │   │
│  │  ┌──────▼──────┐  ┌──────▼──────┐  ┌────────▼────────┐            │   │
│  │  │ToolSelector │  │AdaptiveLearner│  │  ErrorHandler   │            │   │
│  │  │  工具选择器  │  │  自适应学习器  │  │   错误处理器     │            │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Integration Layer (集成层)                      │   │
│  │                    OpenClawIntegration (集成门面)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      External Services (外部服务)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │   LLM    │  │  MCP     │  │  Device  │  │  Vision  │  │  Storage │     │
│  │  大模型   │  │  工具服务 │  │  设备服务 │  │  视觉服务 │  │  存储服务 │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 核心组件详解

### 1. Role Management (角色管理)

```
┌─────────────────────────────────────────┐
│           RoleManager                   │
│  ┌─────────────────────────────────┐   │
│  │      Role Registry              │   │
│  │  ┌─────────┐ ┌─────────┐       │   │
│  │  │smart_home│ │security │ ...   │   │
│  │  │assistant │ │guardian │       │   │
│  │  └────┬────┘ └────┬────┘       │   │
│  │       └───────────┘             │   │
│  │            │                     │   │
│  │       ┌────▼────┐                │   │
│  │       │ Active  │                │   │
│  │       │  Role   │                │   │
│  │       └─────────┘                │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Functions:                             │
│  - register_role()                      │
│  - switch_role()                        │
│  - auto_select_role()                   │
│  - list_roles()                         │
└─────────────────────────────────────────┘
```

**Role 结构**:
```
Role
├── config: RoleConfig
│   ├── name: str
│   ├── description: str
│   ├── personality: str
│   ├── capabilities: Set[RoleCapability]
│   ├── preferred_tools: List[str]
│   └── ...
├── interaction_count: int
├── success_rate: float
└── capability_handlers: Dict[RoleCapability, Callable]
```

### 2. Prompt Template System (提示词模板系统)

```
┌─────────────────────────────────────────┐
│          TemplateEngine                 │
│  ┌─────────────────────────────────┐   │
│  │      Template Registry          │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐       │   │
│  │  │sys  │ │role │ │tools│  ...   │   │
│  │  │base │ │ctx  │ │list │       │   │
│  │  └──┬──┘ └──┬──┘ └──┬──┘       │   │
│  │     └───────┼───────┘           │   │
│  │             │                   │   │
│  │        ┌────▼────┐              │   │
│  │        │ Compose │              │   │
│  │        │ Prompt  │              │   │
│  │        └─────────┘              │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Features:                              │
│  - Variable substitution {{var}}        │
│  - Conditional {% if %}                 │
│  - Loop {% for %}                       │
│  - Template inheritance                 │
└─────────────────────────────────────────┘
```

### 3. Tool Selector (工具选择器)

```
┌─────────────────────────────────────────┐
│           ToolSelector                  │
│  ┌─────────────────────────────────┐   │
│  │     Selection Strategies        │   │
│  │                                 │   │
│  │  ┌──────────┐  ┌──────────┐    │   │
│  │  │  Rule    │  │ Semantic │    │   │
│  │  │  Based   │  │ Matching │    │   │
│  │  └────┬─────┘  └────┬─────┘    │   │
│  │       │             │          │   │
│  │  ┌────▼─────────────▼─────┐    │   │
│  │  │      HYBRID Engine     │    │   │
│  │  │  (Confidence Fusion)   │    │   │
│  │  └───────────┬────────────┘    │   │
│  │              │                  │   │
│  │         ┌────▼────┐             │   │
│  │         │ Ranked  │             │   │
│  │         │ Results │             │   │
│  │         └─────────┘             │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Components:                            │
│  - Keyword mappings                     │
│  - Intent classifier                    │
│  - Performance tracker                  │
│  - Adaptive learner                     │
└─────────────────────────────────────────┘
```

### 4. Context Manager (上下文管理器)

```
┌─────────────────────────────────────────┐
│          ContextManager                 │
│  ┌─────────────────────────────────┐   │
│  │      Session Registry           │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐       │   │
│  │  │sess1│ │sess2│ │sess3│  ...   │   │
│  │  └──┬──┘ └──┬──┘ └──┬──┘       │   │
│  │     └───────┼───────┘           │   │
│  │             │                   │   │
│  │        ┌────▼────┐              │   │
│  │        │Cleanup  │              │   │
│  │        │Service  │              │   │
│  │        └─────────┘              │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Per Session:                           │
│  - Messages: deque[Message]             │
│  - State: ContextState                  │
│  - Entities: Dict                       │
│  - Metadata: Dict                       │
└─────────────────────────────────────────┘
```

**Context State Machine**:
```
        ┌─────────┐
        │  IDLE   │
        └────┬────┘
             │ receive query
             ▼
        ┌─────────┐
        │LISTENING│
        └────┬────┘
             │
             ▼
        ┌─────────┐     ┌─────────┐
        │THINKING │────▶│  ERROR  │
        └────┬────┘     └─────────┘
             │
             ▼
        ┌─────────┐
        │EXECUTING│
        └────┬────┘
             │
             ▼
        ┌─────────┐
        │RESPONDING
        └────┬────┘
             │
             ▼
        ┌─────────┐
        │COMPLETED│
        └─────────┘
```

### 5. Adaptive Learner (自适应学习器)

```
┌─────────────────────────────────────────┐
│          AdaptiveLearner                │
│  ┌─────────────────────────────────┐   │
│  │      Learning Records           │   │
│  │  ┌─────────────────────────┐    │   │
│  │  │  Session │ Query │ Intent │   │   │
│  │  │  ────────┼───────┼─────── │   │   │
│  │  │  sess001 │ 开灯  │turn_on │   │   │
│  │  │  sess002 │ 查看  │view    │   │   │
│  │  │  ...     │ ...   │ ...    │   │   │
│  │  └─────────────────────────┘    │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Analysis Modules:                      │
│  ┌─────────────┐ ┌─────────────┐       │
│  │Intent Pattern│ │Tool Effect │       │
│  │  Analyzer   │ │  Analyzer   │       │
│  └──────┬──────┘ └──────┬──────┘       │
│         │               │              │
│         └───────┬───────┘              │
│                 ▼                      │
│         ┌─────────────┐                │
│         │ Optimization│                │
│         │ Suggestions │                │
│         └─────────────┘                │
└─────────────────────────────────────────┘
```

### 6. Error Handler (错误处理器)

```
┌─────────────────────────────────────────┐
│           ErrorHandler                  │
│  ┌─────────────────────────────────┐   │
│  │      Error Classification       │   │
│  │                                 │   │
│  │  LLM ──▶ LLM_ERROR              │   │
│  │  Net ──▶ NETWORK_ERROR          │   │
│  │  Tool──▶ TOOL_ERROR             │   │
│  │  ... ──▶ ...                    │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Recovery Strategies:                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  Retry  │ │Alternative│ │Simplified│   │
│  │         │ │  Tool    │ │  Prompt  │   │
│  └────┬────┘ └────┬────┘ └────┬────┘   │
│       │           │           │         │
│       └───────────┼───────────┘         │
│                   ▼                     │
│           ┌─────────────┐               │
│           │   Fallback  │               │
│           │   Response  │               │
│           └─────────────┘               │
└─────────────────────────────────────────┘
```

## 数据流

### 正常请求处理流程

```
User Query
    │
    ▼
┌─────────────────┐
│  Auto Role      │◀── RoleManager
│  Selection      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Tool Selection │◀── ToolSelector
│  (Intelligent)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Prompt Generate │◀── TemplateEngine
│   (Dynamic)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLM Processing │◀── External LLM
│   (Streaming)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Tool Execution │◀── MCP Services
│  (If needed)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Record Result  │◀── AdaptiveLearner
│   (Learning)    │
└────────┬────────┘
         │
         ▼
    Response
```

### 错误恢复流程

```
Error Occurs
    │
    ▼
┌─────────────────┐
│ Error Classify  │◀── ErrorHandler
│   (Category)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Select Recovery │
│   Strategy      │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
 Retry    Alternative
 Success?   Tool
    │         │
    ▼         ▼
  Yes      Success?
    │         │
    │    No───┘
    │    │
    ▼    ▼
┌─────────────────┐
│  Default/Fallback│
│    Response     │
└────────┬────────┘
         │
         ▼
    Record Error
```

## 模块间交互

### 1. Agent ↔ RoleManager
```python
# Agent requests role
role = role_manager.auto_select_role(query)
# or
role = role_manager.switch_role("security_guardian")

# Role provides capabilities
can_use = role.can_use_tool("vision_understand")
prompt_additions = role.get_system_prompt_additions()
```

### 2. Agent ↔ ToolSelector
```python
# Agent queries for tools
tool_context = ToolContext(query=query, intent=intent)
selections = tool_selector.select_tools(tool_context, top_k=5)

# Agent records results
tool_selector.record_result(tool_name, success, response_time)
```

### 3. Agent ↔ ContextManager
```python
# Agent manages conversation
context_manager.add_message(session_id, "user", query)
context_manager.update_state(session_id, ContextState.THINKING)
messages = context_manager.get_recent_messages(session_id)
```

### 4. Agent ↔ AdaptiveLearner
```python
# Agent records interaction
record = LearningRecord(
    session_id=session_id,
    query=query,
    intent=intent,
    selected_tools=tools,
    success=success,
)
adaptive_learner.record_interaction(record)

# Agent gets recommendations
recommendations = adaptive_learner.get_tool_recommendations(intent)
```

### 5. Agent ↔ ErrorHandler
```python
# Agent handles errors
result = await error_handler.handle_error(
    error,
    context={"request_id": request_id},
    recovery_context={"original_func": func, "args": args}
)

if result["success"]:
    return result["result"]
```

## 配置架构

```
config/
├── openclaw_config.yaml
│   ├── roles/              # 角色定义
│   ├── prompt_templates/   # 提示词模板
│   ├── tool_selector/      # 工具选择配置
│   ├── context_manager/    # 上下文管理配置
│   ├── adaptive_learner/   # 学习器配置
│   └── error_handler/      # 错误处理配置
│
└── prompt_config.yaml      # 旧版配置（兼容）
```

## 扩展点

### 1. 自定义角色
```python
class CustomRole(Role):
    def execute_capability(self, capability, *args, **kwargs):
        # Custom implementation
        pass
```

### 2. 自定义策略
```python
class CustomStrategy:
    def select(self, context: ToolContext) -> List[ToolSelection]:
        # Custom selection logic
        pass
```

### 3. 自定义恢复策略
```python
async def custom_recovery(record, context, strategy):
    # Custom recovery logic
    return {"success": True, "result": "recovered"}

error_handler.add_recovery_strategy(
    ErrorCategory.CUSTOM,
    RecoveryAction(strategy=FallbackStrategy.CUSTOM, action=custom_recovery)
)
```

## 性能考虑

### 1. 缓存策略
- 角色选择结果缓存（按意图）
- 工具选择结果缓存（按查询）
- 模板渲染结果缓存
- 上下文数据缓存

### 2. 异步处理
- 所有 I/O 操作异步化
- 并发工具调用
- 流式响应处理

### 3. 资源管理
- 上下文自动过期清理
- 学习数据定期归档
- 错误历史定期清理

## 监控指标

### 1. 性能指标
- 角色选择延迟
- 工具选择延迟
- 提示词生成延迟
- 整体响应时间

### 2. 质量指标
- 角色选择准确率
- 工具选择准确率
- 任务成功率
- 用户满意度

### 3. 资源指标
- 活跃上下文数
- 内存使用量
- 学习数据大小
- 错误率

## 安全考虑

1. **输入验证**: 所有用户输入经过验证
2. **权限控制**: 基于角色的工具权限
3. **数据隔离**: 会话间数据隔离
4. **错误信息**: 安全的错误信息展示

## 部署架构

```
┌─────────────────────────────────────────┐
│           Load Balancer                 │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│  Instance │ │  Instance │ │  Instance │
│    #1     │ │    #2     │ │    #3     │
│  ┌─────┐  │ │  ┌─────┐  │ │  ┌─────┐  │
│  │Agent│  │ │  │Agent│  │ │  │Agent│  │
│  └──┬──┘  │ │  └──┬──┘  │ │  └──┬──┘  │
│     │     │ │     │     │ │     │     │
│  ┌──▼──┐  │ │  ┌──▼──┐  │ │  ┌──▼──┐  │
│  │Shared│  │ │  │Shared│  │ │  │Shared│  │
│  │Cache │  │ │  │Cache │  │ │  │Cache │  │
│  └─────┘  │ │  └─────┘  │ │  └─────┘  │
└───────────┘ └───────────┘ └───────────┘
```

## 总结

OpenClaw 框架采用分层架构设计：

1. **表现层**: EnhancedChatAgent 提供统一接口
2. **业务层**: 核心组件处理具体业务逻辑
3. **集成层**: OpenClawIntegration 简化使用
4. **服务层**: 外部服务接口

这种架构确保了：
- ✅ 高内聚、低耦合
- ✅ 易于扩展和维护
- ✅ 支持渐进式迁移
- ✅ 全面的错误处理
- ✅ 持续学习和优化
