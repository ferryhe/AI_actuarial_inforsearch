# React + Flask 拆分与 FastAPI 迁移实施计划

## 一、现状分析

当前仓库同时包含两套前端入口：

- Flask 模板界面：位于 `ai_actuarial/web/templates/`，由 [`ai_actuarial/web/app.py`](/c:/Projects/AI_actuarial_inforsearch/ai_actuarial/web/app.py) 直接渲染页面。
- React SPA：位于 `client/`，通过 [`vite.config.ts`](/c:/Projects/AI_actuarial_inforsearch/vite.config.ts) 开发代理访问 Flask `/api/*`。

当前后端是单体 Flask 应用：

- 主应用文件超过 5,000 行，页面路由、鉴权、任务调度、配置管理、文件管理、日志、用户、RAG、Chat 等逻辑混合在一起。
- `rag_routes.py`、`chat_routes.py` 已有一定模块化，但仍以 Flask 路由注册方式接入。
- React 目前依赖大量 `/api/*` JSON 接口，覆盖 Dashboard / Database / Tasks / Knowledge / KBDetail / Chat / Settings / Users / FileDetail / Profile 等页面。

当前部署现状：

- Docker 容器启动后端，入口为 [`docker-entrypoint.sh`](/c:/Projects/AI_actuarial_inforsearch/docker-entrypoint.sh)，执行 `python -m ai_actuarial web --host 0.0.0.0 --port 5000`。
- [`Dockerfile`](/c:/Projects/AI_actuarial_inforsearch/Dockerfile) 仅为 Python 服务构建镜像。
- [`Caddyfile`](/c:/Projects/AI_actuarial_inforsearch/Caddyfile) 当前将站点根路径代理到 `172.18.0.3:5173`，将 `/api/*`、`/login`、`/email-login` 代理到 Flask `172.18.0.2:5000`。
- 这说明线上/当前部署仍是 `Docker + Caddy`，且前端更像独立 Vite 服务而非静态构建产物。

## 二、需求说明

目标分为两个分支方向：

1. 建立一个仅保留 Flask 全套系统的分支，移除 React 系统，作为现有 Flask 版本归档和后续回退基线。
2. 建立一个新的迁移分支，完成整体技术栈切换：
   - 前端：React + Vite
   - 后端：FastAPI
   - 通信：JSON API（Fetch / Axios）
   - 部署：前端改为静态资源部署，后端独立服务，保留 Docker + Caddy 的当前生产思路并调整为适配新架构
3. 检查并迁移后台 Python 功能，确保 React 页面最终都能正常调用。
4. 完成自动化测试、测试文档和实现报告。

本次范围内：

- 包含：分支切分、React/Flask 职责拆分、FastAPI 后端落地、核心 API 与鉴权迁移、部署配置调整、自动化测试更新、文档输出。
- 不包含：重新设计业务功能、替换核心 crawler/RAG/storage 业务逻辑、变更数据库产品选型。

## 三、技术方案

### 方案总览

采用“两分支 + 分阶段迁移”的方式，避免一次性替换导致回退困难。

### 分支策略

- 分支 A：`archive/flask-only-system`
  - 基于当前 `main`
  - 删除 `client/`、Vite/Node 相关文件和 React 构建配置
  - 保留 Flask 模板页面、Flask API、Docker + Caddy 的 Flask 单体部署方式
  - 作为旧架构归档基线

- 分支 B：`feature/react-fastapi-migration`
  - 基于当前 `main`
  - 保留 `client/`
  - 新增 `ai_actuarial/api/` 或 `ai_actuarial/fastapi_app/` 模块
  - 逐步把 Flask JSON API 迁移到 FastAPI
  - 最终将 React 作为唯一前端，Flask 模板界面退出运行路径

### 迁移原则

- 先迁移 JSON API，再清理 Flask 模板页面。
- 业务层尽量复用现有 `storage*`、`crawler`、`catalog*`、`chatbot`、`rag`、`collectors` 等 Python 模块，避免改核心算法。
- 将 Flask 中的“路由控制层”拆到 FastAPI Router；将共用鉴权、任务状态、配置读写、响应模型逐步模块化。
- 保持 React 现有 API contract 尽量稳定，优先减少前端大改量。

### FastAPI 落地结构

建议新增结构：

```text
ai_actuarial/
  api/
    app.py
    deps.py
    schemas/
    routers/
      auth.py
      users.py
      files.py
      tasks.py
      config.py
      rag.py
      chat.py
      logs.py
```

建议落地方式：

- `FastAPI` + `Pydantic` 管理请求/响应模型
- `CORSMiddleware` 支撑本地 React 开发
- 使用 `BackgroundTasks` 或线程包装现有长任务逻辑
- 鉴权先兼容当前 token/session 语义，避免一次性重写权限系统

### 部署调整方案

当前部署判断正确：现状是 `docker + caddy`。

迁移后目标部署建议：

- 前端：Vite 构建产物输出为静态文件，由 Caddy 或 Nginx 直接托管
- 后端：FastAPI 通过 `uvicorn` 或 `gunicorn + uvicorn workers` 独立运行
- Caddy：根路径指向前端静态目录；`/api/*` 反向代理到 FastAPI
- Docker：至少拆为两个运行单元
  - `frontend`：构建静态资源
  - `backend`：FastAPI 服务

## 四、实施步骤

### Phase 1: Flask-only 归档分支

**时间估算**: 0.5-1 天

**步骤**:

- [ ] 从当前 `main` 创建 `archive/flask-only-system`
- [ ] 删除 `client/`、`package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig.json`
- [ ] 调整 README / Docker / Caddy 说明，明确该分支为纯 Flask 版本
- [ ] 运行 Flask 相关测试，确认纯 Flask 分支可启动

### Phase 2: FastAPI 后端骨架

**时间估算**: 1-2 天

**步骤**:

- [ ] 从当前 `main` 创建 `feature/react-fastapi-migration`
- [ ] 新建 FastAPI 应用入口与路由结构
- [ ] 提取 Flask 公共逻辑到共享服务层
- [ ] 先迁移 React 必需的基础接口：认证、状态、文件列表、分类、设置、任务列表
- [ ] 增加 FastAPI 启动命令与开发说明

### Phase 3: React 全量 API 对接

**时间估算**: 2-4 天

**步骤**:

- [ ] 梳理 React 页面依赖接口并逐页验证
- [ ] 迁移 tasks / settings / file detail / knowledge base / chat / users 等接口
- [ ] 必要时统一响应格式，减少 React 兼容分支
- [ ] 去除 React 对 Flask 模板页 `/login`、`/register` 等混合依赖

### Phase 4: 部署迁移

**时间估算**: 0.5-1 天

**步骤**:

- [ ] 更新 Dockerfile 或拆分前后端镜像
- [ ] 更新 Caddy 配置为静态前端 + FastAPI 代理
- [ ] 校验本地开发代理与生产部署路径一致性
- [ ] 更新 README 与服务启动文档

### Phase 5: 测试与文档

**时间估算**: 1 天

**步骤**:

- [ ] 跑 Python 自动化测试并修复回归
- [ ] 增补 FastAPI API 测试
- [ ] 构建 React 并做接口联调验证
- [ ] 输出测试指南、开发日志、实现报告

## 五、关键决策点

### 决策1: 迁移分支是否基于当前 `main`

**选项**: 基于 Flask-only 分支继续迁移 vs 基于当前 `main` 单独迁移

**选择**: 两个目标分支都基于当前 `main`

**理由**:

- Flask-only 分支是归档基线，不应该带入 FastAPI 改造痕迹
- FastAPI 迁移应保留当前 React 代码，直接在现有双系统基础上迁移成本更低

### 决策2: 是否保留 Flask 模板页面并行运行

**选项**: 并行保留 vs 迁移后移出主运行路径

**选择**: 迁移分支中先保留代码，后退出主运行路径

**理由**:

- React 当前仍依赖部分 Flask 登录/注册路径语义
- 先兼容再清理可减少一次性破坏
- 最终部署目标仍应是 React 唯一前端

### 决策3: 是否重写业务层

**选项**: 重写 storage/crawler/rag 服务 vs 仅重写 Web/API 层

**选择**: 仅重写 Web/API 层

**理由**:

- 用户目标是技术栈切换，不是重做业务逻辑
- 当前 Python 业务层已配套较多测试，复用更稳妥

## 六、风险与注意事项

- Flask `app.py` 体量大，很多辅助函数与路由耦合，迁移时需要先抽公共依赖。
- 当前 React 调用接口很多，且响应结构并不完全统一，迁移时需要做契约梳理。
- 任务调度、后台线程、日志、token/session 鉴权是高风险区域，不能只迁页面接口。
- `Caddyfile` 当前根路径仍指向 Vite 开发服务，生产部署方式需要同步纠正。
- 如果一次性移除 Flask 模板而未补齐 React 登录/注册语义，会导致认证路径断裂。

## 七、成功标准

- [ ] 存在可运行的 `archive/flask-only-system` 分支
- [ ] 存在可运行的 `feature/react-fastapi-migration` 分支
- [ ] React 所有主页面能通过 FastAPI 正常调用
- [ ] Docker + Caddy 部署配置已更新并可解释
- [ ] 自动化测试通过
- [ ] 文档产出完整

## 八、时间估算

**总计**: 4-8 天

## 九、执行说明

本次实施将按以下顺序推进：

1. 先创建并整理 Flask-only 归档分支
2. 回到当前基线创建 FastAPI 迁移分支
3. 分批迁移 API 与部署
4. 通过自动化测试后补齐文档

若你确认该计划，我再开始 Phase 1 实施。
