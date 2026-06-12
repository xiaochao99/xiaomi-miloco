# 热更新脚本说明

## 概述

Miloco 热更新系统由两个 PowerShell 脚本组成，配合后端 `system_controller.py` 实现在线增量更新：

| 脚本 | 功能 |
|------|------|
| `build_hotfix.ps1` | 构建增量更新包（`.tar.gz`） |
| `upload_release_github.ps1` | 将更新包上传到 GitHub Release |

**前置条件**：
- Windows 系统（PowerShell 5.1+）
- 已安装 Node.js（用于前端构建）
- `tar` 命令可用（Windows 10 1803+ 内置）
- Git 已配置（上传脚本需要）

---

## build_hotfix.ps1 —— 构建热更新包

### 基本用法

```powershell
# 自动递增 patch 版本号（v0.0.4 → v0.0.5）
.\scripts\build_hotfix.ps1

# 指定版本号
.\scripts\build_hotfix.ps1 v1.0.3
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `Version` | `string` | 目标版本号（如 `v1.0.3`）。不指定则自动递增当前的 patch 版本 |
| `-NoFrontend` | `switch` | 跳过前端构建（适用于仅后端代码变更的情况） |
| `-IncludeConfig` | `switch` | 将 `config/` 目录中的 YAML 配置文件也打包进更新包 |
| `-PipSync` | `switch` | 在 `manifest.json` 中标记需要同步 pip 依赖。容器热更新时会自动执行 `pip install -e /app/miloco_server` |

### 打包内容

热更新包 `miloco-hotfix-{Version}.tar.gz` 包含：

```
miloco-hotfix-v1.0.3/
├── VERSION                          # 版本号文件
├── manifest.json                    # 元数据（文件清单、配置信息）
└── backend/
    ├── miloco_server/               # Python 源码（排除 __pycache__/ 和 .pyc）
    │   └── static/                  # 前端构建产物
    ├── miot_kit/                    # 小米 IoT SDK
    ├── config/                      # （可选）-IncludeConfig 时才包含
    └── start_server.py              # 启动脚本
```

### 输出

构建完成后在 `dist/` 目录生成：

```
dist/
├── miloco-hotfix-v1.0.3.tar.gz          # 热更新包
├── miloco-hotfix-v1.0.3.tar.gz.sha256   # SHA256 校验文件
└── manifest.json                        # 元数据（也会随包发布）
```

### 典型场景

```powershell
# 场景1：常规前后端更新
.\scripts\build_hotfix.ps1

# 场景2：仅后端代码修改，跳前端
.\scripts\build_hotfix.ps1 -NoFrontend

# 场景3：新增了 Python 依赖（pyproject.toml 有变化）
.\scripts\build_hotfix.ps1 -PipSync

# 场景4：需要同时更新配置文件
.\scripts\build_hotfix.ps1 -IncludeConfig

# 场景5：同时指定版本、pip 依赖和配置更新
.\scripts\build_hotfix.ps1 v1.0.5 -PipSync -IncludeConfig
```

---

## upload_release_github.ps1 —— 上传到 GitHub Release

### 基本用法

```powershell
# 使用默认版本号上传
.\scripts\upload_release_github.ps1

# 指定版本号
.\scripts\upload_release_github.ps1 -Version "v1.0.3"

# 预览模式（不实际执行，仅打印将执行的操作）
.\scripts\upload_release_github.ps1 -Version "v1.0.3" -DryRun
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-Version` | `string` | `v1.0.2` | 要发布的版本号（需与 `build_hotfix.ps1` 构建的版本一致） |
| `-Token` | `string` | （内置） | GitHub Personal Access Token |
| `-Owner` | `string` | `xiaochao99` | GitHub 仓库所有者 |
| `-Repo` | `string` | `xiaomi-miloco` | GitHub 仓库名称 |
| `-DryRun` | `switch` | `false` | 预览模式，只打印操作不执行 |
| `-PushToGitHub` | `switch` | `false` | 上传前先将代码 push 到 GitHub |

### 执行流程

1. **检查/创建 Git Tag** —— 若 `v1.0.3` 标签不存在则基于 `main` 分支 HEAD 自动创建
2. **删除已有 Release** —— 如果该 Tag 已有 Release，先删除（实现覆盖更新）
3. **创建 Release** —— 从 `CHANGELOG.md` 读取当前版本的更新说明作为 Release Notes
4. **上传资源文件** —— 上传 `.tar.gz`、`.sha256`、`manifest.json` 三个文件
5. **验证** —— 查询 Release 确认资源已正确上传

### Release Notes 来源

脚本会读取项目根目录的 `CHANGELOG.md`，提取当前版本（如 `## v1.0.3`）对应章节的内容作为 Release Notes。如果找不到 `CHANGELOG.md` 则使用默认模板。

### 典型场景

```powershell
# 场景1：常规发布（使用默认版本）
.\scripts\upload_release_github.ps1

# 场景2：预览检查（先看看会做什么）
.\scripts\upload_release_github.ps1 -Version "v1.0.3" -DryRun

# 场景3：推代码并发布（一站式）
.\scripts\upload_release_github.ps1 -Version "v1.0.3" -PushToGitHub
```

---

## 完整工作流

一个完整的热更新发布流程如下：

```powershell
# Step 1: 构建更新包（自动递增版本号或指定版本）
.\scripts\build_hotfix.ps1 v1.0.3

# Step 2: 上传到 GitHub Release（容器内自动可检测到）
.\scripts\upload_release_github.ps1 -Version "v1.0.3"

# 用户在容器内通过 Web 设置页面"检查更新" → "应用更新"即可
# 或登录时自动检测到新版本，弹出更新提示
```

### 本地文件更新（离线）

```powershell
# Step 1: 构建更新包
.\scripts\build_hotfix.ps1 v1.0.3

# Step 2: 不通过 GitHub，直接在 Web 设置页面
# 点击「上传本地更新包」→ 选择 dist/miloco-hotfix-v1.0.3.tar.gz → 确认更新
```

---

## manifest.json 结构

构建脚本生成的 `manifest.json` 结构如下：

```json
{
  "schema_version": "1.0",
  "version": "v1.0.3",
  "commit_message": "Incremental update v1.0.3",
  "timestamp": "2026-06-12T09:30:00Z",
  "requires_full_rebuild": false,
  "pip_sync": false,
  "changes": {
    "backend": {
      "has_changes": true,
      "python_files": ["start_server.py", "miloco_server/..."],
      "frontend_rebuilt": true,
      "has_config": false,
      "config_files": [],
      "startup_scripts": []
    }
  }
}
```

关键字段说明：
- `pip_sync: true` — 容器更新时会自动运行 `pip install -e /app/miloco_server`
- `has_config: true` — 前端会展示「同时更新配置文件」复选框
