# AI Chatbot API 接口文档

## 概述

本文档详细描述 AI Chatbot 项目的后端 API 接口，包括认证、会话管理和聊天功能。

---

## 基础信息

- **API 前缀**: `/api/v1`
- **认证方式**: JWT Bearer Token
- **内容类型**: `application/json`
- **健康检查**: `GET /health`

---

## 目录

1. [认证接口](#认证接口)
2. [会话管理](#会话管理)
3. [聊天接口](#聊天接口)
4. [管理员接口](#管理员接口)
5. [根接口](#根接口)

---

## 认证接口

### 1. 注册用户

**POST** `/api/v1/auth/register`

注册新用户。

#### 请求体
```json
{
    "email": "string (必填, 邮箱格式)",
    "password": "string (必填, 密码要求见下方)",
    "username": "string (可选, 显示名称)"
}
```

**密码要求**:
- 至少8位
- 包含大写字母
- 包含小写字母
- 包含数字
- 包含特殊字符: `!@#$%^&*(),.?":{}|<>[]`

#### 成功响应 (200)
```json
{
    "id": "integer (用户ID)",
    "email": "string (用户邮箱)",
    "username": "string (用户名，可能为null)",
    "token": "string (JWT访问令牌)"
}
```

#### 错误响应
- `400`: Email already registered (邮箱已注册)
- `422`: 密码强度不足或参数校验失败

---

### 2. 用户登录

**POST** `/api/v1/auth/login`

用户登录获取访问令牌。

#### 请求体 (x-www-form-urlencoded)
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 用户邮箱 |
| password | string | 是 | 用户密码 |
| grant_type | string | 否 | 默认 "password" |

#### 成功响应 (200)
```json
{
    "access_token": "string (JWT访问令牌)",
    "token_type": "string (令牌类型, 'bearer')"
}
```

#### 错误响应
- `401`: 邮箱或密码错误

---

## 会话管理

### 3. 创建会话

**POST** `/api/v1/auth/session`

为当前用户创建新的聊天会话。

#### 请求头
```
Authorization: Bearer <access_token>
```

#### 成功响应 (200)
```json
{
    "session_id": "string (会话ID)",
    "name": "string (会话名称，可能为空)",
    "token": {
        "access_token": "string (会话级JWT令牌)",
        "token_type": "string"
    }
}
```

---

### 4. 获取用户会话列表

**GET** `/api/v1/auth/sessions`

获取当前用户的所有会话。

#### 请求头
```
Authorization: Bearer <access_token>
```

#### 成功响应 (200)
```json
[
    {
        "session_id": "string (会话ID)",
        "name": "string (会话名称，可能为空)",
        "token": {
            "access_token": "string (会话令牌)",
            "token_type": "string"
        }
    }
]
```

---

### 5. 更新会话名称

**PATCH** `/api/v1/auth/session/{session_id}/name`

更新指定会话的名称。

#### 请求头
```
Authorization: Bearer <access_token>
```

#### 请求体
```json
{
    "name": "string (新的会话名称)"
}
```

#### 成功响应 (200)
```json
{
    "session_id": "string",
    "name": "string (更新后的名称)",
    "token": {
        "access_token": "string",
        "token_type": "string"
    }
}
```

---

### 6. 删除会话

**DELETE** `/api/v1/auth/session/{session_id}`

删除指定会话及其所有消息。

#### 请求头
```
Authorization: Bearer <access_token>
```

#### 成功响应 (200)
```json
{
    "message": "Session deleted successfully"
}
```

---

## 聊天接口

### 7. 发送消息 (非流式)

**POST** `/api/v1/chatbot/chat`

发送消息并获取AI回复（非流式）。

#### 请求头
```
Authorization: Bearer <session_token>
```

#### 请求体
```json
{
    "messages": [
        {
            "role": "string (角色: 'user' 或 'assistant')",
            "content": "string (消息内容)"
        }
    ]
}
```

#### 成功响应 (200)
```json
{
    "messages": [
        {
            "role": "string",
            "content": "string"
        }
    ]
}
```

---

### 8. 发送消息 (流式)

**POST** `/api/v1/chatbot/chat/stream`

发送消息并获取AI的流式回复。

#### 请求头
```
Authorization: Bearer <session_token>
```

#### 请求体
```json
{
    "messages": [
        {
            "role": "string",
            "content": "string"
        }
    ]
}
```

#### 响应格式 (SSE - Server-Sent Events)
```
data: {"content": "回复内容片段", "done": false}
data: {"content": "更多内容", "done": false}
data: {"content": "", "done": true}
```

---

### 9. 获取会话消息

**GET** `/api/v1/chatbot/messages`

获取当前会话的所有消息记录。

#### 请求头
```
Authorization: Bearer <session_token>
```

#### 成功响应 (200)
```json
{
    "messages": [
        {
            "role": "string",
            "content": "string"
        }
    ]
}
```

---

### 10. 清空会话消息

**DELETE** `/api/v1/chatbot/messages`

清空当前会话的所有消息。

#### 请求头
```
Authorization: Bearer <session_token>
```

#### 成功响应 (200)
```json
{
    "message": "Messages deleted successfully"
}
```

---

## 管理员接口

### 11. 获取所有用户

**GET** `/api/v1/auth/users`

获取系统中所有用户（管理员权限）。

#### 成功响应 (200)
```json
[
    {
        "id": "integer",
        "email": "string",
        "username": "string",
        "created_at": "string (ISO时间戳)"
    }
]
```

---

### 12. 删除用户

**DELETE** `/api/v1/auth/users/{user_id}`

删除指定用户（管理员权限）。

#### 成功响应 (200)
```json
{
    "message": "User deleted successfully"
}
```

---

### 13. 获取所有会话

**GET** `/api/v1/auth/all-sessions`

获取系统中所有会话（管理员权限）。

#### 成功响应 (200)
```json
[
    {
        "id": "string",
        "name": "string",
        "user_id": "integer",
        "created_at": "string (ISO时间戳)"
    }
]
```

---

### 14. 管理员删除会话

**DELETE** `/api/v1/auth/admin/session/{session_id}`

删除指定会话（管理员权限）。

#### 成功响应 (200)
```json
{
    "message": "Session deleted successfully"
}
```

---

## 根接口

### 15. 首页接口

**GET** `/`

获取项目基础信息。

#### 成功响应 (200)
```json
{
    "name": "string (项目名称)",
    "version": "string (版本号)",
    "status": "string (运行状态)",
    "环境": "string (开发/测试/生产)",
    "接口文档地址": "/docs",
    "官方文档地址": "/redoc"
}
```

---

### 16. 健康检查

**GET** `/health`

检查服务和数据库状态。

#### 成功响应 (200)
```json
{
    "status": "string (正常/服务异常)",
    "版本": "string",
    "环境": "string",
    "组件状态": {
        "接口服务": "string",
        "数据库": "string"
    },
    "当前时间": "string (ISO时间戳)"
}
```

---

## 错误响应格式

所有接口的错误响应统一格式：

```json
{
    "detail": "string (错误描述)"
}
```

---

## 状态码说明

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未授权（令牌无效或缺失） |
| 404 | 资源未找到 |
| 422 | 数据校验失败 |
| 500 | 服务器内部错误 |

---

## 使用流程示例

### 完整聊天流程

1. **注册**: `POST /api/v1/auth/register`
2. **登录**: `POST /api/v1/auth/login` → 获取 `access_token`
3. **创建会话**: `POST /api/v1/auth/session` → 获取 `session_token`
4. **发送消息**: 
   - 流式: `POST /api/v1/chatbot/chat/stream`
   - 非流式: `POST /api/v1/chatbot/chat`
5. **获取消息**: `GET /api/v1/chatbot/messages`
6. **切换会话**: 选择会话列表中的 `session_token`，重新发送消息

---

## 注意事项

1. **令牌类型**: 
   - 登录后获取的是用户级令牌，用于会话管理
   - 创建会话后获取的是会话级令牌，用于聊天接口
   
2. **令牌有效期**: JWT令牌有过期时间，需要重新登录

3. **限流**: 所有接口都有限流保护，超出频率会被暂时封禁

4. **密码强度**: 注册时密码必须满足复杂度要求