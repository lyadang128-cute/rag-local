# RAG 知识库 v0.3.0 — 多知识库 + 账号系统升级文档

## 新增功能

### 1. 知识库创建与管理
- `POST /api/v1/kb/create` — 创建知识库（名称、部门、权限级别、描述）
- KB 列表合并双来源（knowledge_bases 表 + 文档表自动生成）
- 前端 KB 管理页新增「+ 新建知识库」按钮 + 弹窗表单

### 2. 分部门权限模型
- KB 三级权限：`1=全员可见` / `2=部门可见` / `3=仅管理员`
- 角色三级：`admin` / `manager` / `employee`
- KB 列表自动按用户角色和部门过滤
- 创建/删除 KB 需 admin 或 manager 权限
- chunk 入库时自动 stamp 部门+权限到 payload

### 3. 账号登录系统
- `POST /api/v1/auth/register` — 注册
- `POST /api/v1/auth/login` — 登录，返回 JWT
- `GET /api/v1/auth/me` — 获取当前用户信息
- `JWTAuthMiddleware` — 自动解析 Bearer token，注入 `request.state.user`
- 前端登录页 + 路由守卫 + API 拦截器 + 侧边栏用户信息 + 登出

## 改动文件

| 文件 | 改动 |
|------|------|
| `backend/requirements.txt` | +python-jose, passlib, bcrypt |
| `backend/app/config.py` | +jwt_secret, jwt_algorithm, jwt_expire_hours |
| `backend/app/utils/db.py` | +knowledge_bases 表, +users 表, +CRUD 方法 |
| `backend/app/models/schemas.py` | +KBCreateRequest, KBOut |
| `backend/app/api/kb.py` | +POST /kb/create, 权限过滤, 角色保护 |
| `backend/app/api/auth.py` | **新建** — 注册/登录/用户信息 |
| `backend/app/api/router.py` | 注册 auth 路由 |
| `backend/app/middleware/auth.py` | APIKeyMiddleware → JWTAuthMiddleware |
| `backend/app/middleware/__init__.py` | 更新导出 |
| `backend/app/main.py` | 更新中间件引用 |
| `backend/app/tasks/ingestion.py` | 入库时 stamp 部门+权限到 chunk |
| `frontend/src/composables/useAuth.js` | **新建** — auth 状态管理 |
| `frontend/src/views/Login.vue` | **新建** — 登录/注册页 |
| `frontend/src/views/KBManagement.vue` | +新建按钮+弹窗+权限标签 |
| `frontend/src/views/Layout.vue` | +侧边栏用户信息+登出按钮 |
| `frontend/src/views/Search.vue` | KB 列表适配新格式 |
| `frontend/src/views/Chat.vue` | KB 列表适配新格式 |
| `frontend/src/views/Documents.vue` | KB 列表适配新格式(5处) |
| `frontend/src/router/index.js` | +/login 路由, +beforeEach 守卫 |
| `frontend/src/api/index.js` | +Auth 拦截器, +createKB, +SSE token |

## 权限规则速查

| 角色 | 数值 | 可见 KB 级别 | 可创建/删除 KB |
|------|------|-------------|---------------|
| admin | 3 | 全部(1+2+3) | ✅ |
| manager | 2 | 公开(1) + 本部门(2) | ✅ |
| employee | 1 | 公开(1) | ❌ |

## 升级步骤

```bash
# 1. 装新依赖
cd backend
.venv/Scripts/pip install -r requirements.txt

# 2. 重启后端
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 9090

# 3. 前端正常 npm run dev
cd ../frontend && npm run dev
```

## 使用流程

1. 打开 `http://localhost:5173` → 自动跳转登录页
2. 点「去注册」→ 创建 admin 账号（角色选"管理员"）
3. 登录 → 进入对话页
4. 切到「知识库」→ 点「+ 新建知识库」→ 创建部门 KB
5. 切到「文档管理」→ 上传时选择目标 KB
6. 注册 employee 账号 → 登录 → KB 列表只有公开 KB

## 已知问题

- bcrypt 5.x 与 passlib 不兼容，固定 bcrypt>=4.0,<5.0
- 注册接口 curl 传中文 JSON 需用文件方式（`-d @file.json`）
- Chat SSE 和 Search 接口暂未加强制权限校验（KB 列表已过滤，靠前端控制 kb_name 选择范围）
