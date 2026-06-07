# AI Chatbot 前端开发指导文档

## 概述

本文档详细介绍 AI Chatbot 前端项目的开发规范、架构设计和实现指南。

---

## 目录

1. [项目结构](#项目结构)
2. [技术栈](#技术栈)
3. [核心功能](#核心功能)
4. [组件设计](#组件设计)
5. [状态管理](#状态管理)
6. [API 调用](#api调用)
7. [开发流程](#开发流程)
8. [最佳实践](#最佳实践)

---

## 项目结构

```
frontend/
├── index.html          # 主入口页面
└── (可选) src/         # Vue组件目录（如需模块化）
    ├── components/     # 可复用组件
    ├── services/       # API服务
    ├── stores/         # 状态管理
    └── utils/          # 工具函数
```

---

## 技术栈

| 分类 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | Vue.js | 3.x | 渐进式 JavaScript 框架 |
| UI | Tailwind CSS | 3.x | 原子化 CSS 框架 |
| 图标 | Font Awesome | 6.x | 图标库 |
| 构建 | 原生 | - | 无需构建工具，直接运行 |

---

## 核心功能

### 功能模块

1. **认证模块**
   - 用户登录/注册
   - JWT 令牌管理
   - 自动登录状态恢复

2. **会话管理**
   - 创建新会话
   - 会话列表展示
   - 切换会话
   - 删除会话

3. **聊天功能**
   - 消息发送/接收
   - 流式响应支持
   - 消息历史记录
   - 清空聊天记录

4. **设置模块**
   - API 地址配置
   - 流式响应开关
   - 设置持久化

---

## 组件设计

### 组件结构

```
┌─────────────────────────────────────────────────────┐
│                    Header                          │
│  [Logo] [Title]              [New Session] [User]  │
├─────────────────────────────────────────────────────┤
│  Sidebar          │              Main Content       │
│  ┌─────────────┐  │  ┌─────────────────────────┐   │
│  │ Session     │  │  │ Session Title           │   │
│  │ List        │  │  ├─────────────────────────┤   │
│  │             │  │  │                         │   │
│  │ [Session 1] │  │  │     Message List        │   │
│  │ [Session 2] │  │  │                         │   │
│  │ [Session 3] │  │  │                         │   │
│  │             │  │  ├─────────────────────────┤   │
│  └─────────────┘  │  │ Input Area             │   │
│                   │  └─────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 组件职责

| 组件 | 职责 | 状态管理 |
|------|------|----------|
| Header | 顶部导航，新建会话，用户信息 | 全局状态 |
| Sidebar | 会话列表展示与管理 | sessions, currentSession |
| ChatArea | 消息列表与输入框 | messages, messageInput |
| AuthModal | 登录/注册弹窗 | authForm, isLoginMode |
| SettingsModal | 设置弹窗 | settings |
| Toast | 全局提示 | toast |

---

## 状态管理

### 核心状态

```javascript
// 用户认证状态
isLoggedIn: boolean      // 是否已登录
userEmail: string        // 用户邮箱/名称

// 会话状态
sessions: Array          // 会话列表
currentSession: string   // 当前会话ID
messages: Array          // 当前会话消息

// UI状态
messageInput: string     // 输入框内容
isLoading: boolean       // 加载状态
streamingEnabled: boolean // 流式响应开关

// 设置
settings: {
    apiUrl: string,      // API地址
    streamingEnabled: boolean
}
```

### 状态持久化

```javascript
// localStorage 存储键
'chatbot-auth': JSON.stringify({ token, user })  // 认证信息
'chatbot-settings': JSON.stringify(settings)     // 设置
'sessionToken': string                           // 当前会话令牌
```

---

## API 调用

### 调用流程

```
用户操作 → API服务 → HTTP请求 → 响应处理 → 更新状态 → UI更新
```

### API 服务封装

```javascript
class ApiService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async request(method, endpoint, data = null, useAuth = true) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = { 'Content-Type': 'application/json' };
        
        if (useAuth) {
            const token = localStorage.getItem('sessionToken');
            if (token) headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(url, { method, headers, body: data ? JSON.stringify(data) : null });
        const text = await response.text();
        
        if (!response.ok) {
            let error = `HTTP ${response.status}`;
            try {
                const json = JSON.parse(text);
                error = json.detail || error;
            } catch {}
            return { success: false, error };
        }

        return { success: true, data: text ? JSON.parse(text) : {} };
    }
}
```

### 常用 API 调用示例

```javascript
// 注册
await api.request('POST', '/api/v1/auth/register', { email, password, username }, false);

// 登录 (特殊: x-www-form-urlencoded)
const formData = new URLSearchParams({ email, password });
const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData
});

// 创建会话
await api.request('POST', '/api/v1/auth/session');

// 发送消息（非流式）
await api.request('POST', '/api/v1/chatbot/chat', { messages });

// 发送消息（流式）
const response = await fetch(`${apiUrl}/api/v1/chatbot/chat/stream`, {
    method: 'POST',
    headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ messages })
});

const reader = response.body.getReader();
const decoder = new TextDecoder('utf-8');

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    // 解析 SSE 格式数据...
}
```

---

## 开发流程

### 环境要求

- 现代浏览器（Chrome, Firefox, Safari, Edge）
- 无需 Node.js，纯前端静态文件

### 启动方式

1. **开发模式**: 直接用浏览器打开 `index.html`
2. **生产部署**: 部署到静态文件服务器（如 Nginx, Apache）

### 开发步骤

1. **初始化**: 在 `onMounted` 中加载设置和认证状态
2. **认证**: 登录/注册成功后保存令牌到 localStorage
3. **会话**: 创建会话后切换到新会话并加载消息
4. **聊天**: 发送消息时处理流式/非流式响应
5. **清理**: 退出登录时清除 localStorage

---

## 最佳实践

### 错误处理

```javascript
// 统一错误处理
async function safeRequest(fn) {
    try {
        return await fn();
    } catch (error) {
        showToast(error.message, 'error');
        return { success: false, error: error.message };
    }
}

// 请求失败时的提示
if (!result.success) {
    showToast(result.error, 'error');
    return;
}
```

### 性能优化

```javascript
// 消息渲染优化：使用 Vue 的 v-for 并指定 key
<div v-for="(msg, index) in messages" :key="index">
    <!-- 消息内容 -->
</div>

// 滚动优化：使用 nextTick 确保 DOM 更新后再滚动
function scrollToBottom() {
    nextTick(() => {
        const container = document.querySelector('.message-container');
        if (container) container.scrollTop = container.scrollHeight;
    });
}
```

### 安全注意事项

1. **令牌安全**:
   - 使用 `Bearer` 认证
   - 令牌存储在 `localStorage`
   - 注意 XSS 攻击防护

2. **输入校验**:
   - 前端校验邮箱格式
   - 密码强度提示
   - 消息内容长度限制

3. **HTTPS**:
   - 生产环境必须使用 HTTPS
   - 防止令牌被中间人攻击窃取

### 用户体验

1. **加载状态**:
   - 发送消息时显示加载动画
   - 网络请求时禁用按钮

2. **Toast 提示**:
   - 操作成功/失败提示
   - 3秒自动消失

3. **响应式设计**:
   - 适配不同屏幕尺寸
   - 移动端友好

---

## 代码规范

### 命名规范

- **变量**: 驼峰命名（camelCase）
- **组件**: 大驼峰命名（PascalCase）
- **文件**: 小写加横线（kebab-case）

### 注释规范

```javascript
/**
 * 发送消息到后端
 * @param {string} content - 消息内容
 * @returns {Promise} - 返回消息响应
 */
async function sendMessage(content) {
    // 实现代码
}
```

### 代码结构

```javascript
// 按功能模块组织
const state = { /* 状态定义 */ };
const computed = { /* 计算属性 */ };
const methods = { /* 方法定义 */ };
const lifecycle = { /* 生命周期钩子 */ };
```

---

## 测试指南

### 功能测试

| 测试项 | 测试步骤 | 预期结果 |
|--------|----------|----------|
| 注册 | 输入有效邮箱密码 | 注册成功，自动登录 |
| 登录 | 输入正确凭据 | 登录成功，显示会话列表 |
| 新建会话 | 点击新建会话按钮 | 创建成功，切换到新会话 |
| 发送消息 | 输入消息并发送 | 收到 AI 回复 |
| 流式响应 | 开启流式开关发送消息 | 消息逐字显示 |
| 删除会话 | 点击删除按钮 | 会话被删除 |
| 设置保存 | 修改设置并保存 | 设置持久化到本地 |

### 边界测试

1. **网络异常**: 模拟断网，检查错误提示
2. **无效令牌**: 使用过期令牌，检查重新登录提示
3. **空输入**: 发送空消息，检查输入校验
4. **大量消息**: 发送多条消息，检查性能和滚动

---

## 部署指南

### 静态部署

1. 将 `frontend/` 目录上传到服务器
2. 配置 Nginx 或 Apache 指向该目录
3. 配置 HTTPS（推荐使用 Let's Encrypt）

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # 重定向到 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    root /path/to/frontend;
    index index.html;
    
    # API 代理
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 常见问题

### Q1: 登录后刷新页面状态丢失？

**原因**: 没有在初始化时加载 localStorage 中的认证信息。

**解决**: 在 `onMounted` 钩子中读取 localStorage 并恢复状态。

```javascript
onMounted(() => {
    const auth = localStorage.getItem('chatbot-auth');
    if (auth) {
        const parsed = JSON.parse(auth);
        if (parsed.token && parsed.user) {
            isLoggedIn.value = true;
            userEmail.value = parsed.user.email;
        }
    }
});
```

### Q2: 流式响应没有正确解析？

**原因**: SSE 格式解析错误。

**解决**: 正确处理 `data:` 前缀和 `\n\n` 分隔符。

```javascript
const lines = chunk.split('\n\n');
for (const line of lines) {
    if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        // 处理数据...
    }
}
```

### Q3: 消息发送后没有响应？

**原因**: 
1. API 地址配置错误
2. 会话令牌过期
3. 后端服务未启动

**解决**: 
1. 检查设置中的 API 地址
2. 检查浏览器控制台的网络请求
3. 确认后端服务正常运行

---

## 扩展建议

### 未来功能

1. **消息编辑**: 支持编辑已发送的消息
2. **消息引用**: 支持引用回复特定消息
3. **文件上传**: 支持上传图片或文件
4. **主题切换**: 支持亮色/暗色主题
5. **消息搜索**: 支持搜索历史消息
6. **多语言**: 支持多语言切换

### 技术升级

1. **Vue 组件化**: 将单文件拆分为多个组件
2. **状态管理**: 引入 Pinia 进行更复杂的状态管理
3. **构建工具**: 使用 Vite 进行构建优化
4. **类型安全**: 使用 TypeScript
5. **测试框架**: 引入 Vitest 进行单元测试

---

## 联系与支持

如有问题或建议，请联系项目维护者。