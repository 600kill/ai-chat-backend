"""
极简接口测试文件 - 用于验证核心API功能
"""

import pytest
import httpx
import uuid

BASE_URL = "http://localhost:8000"


def test_root_endpoint():
    """测试根接口"""
    with httpx.Client() as client:
        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "status" in data


def test_health_endpoint():
    """测试健康检查接口"""
    with httpx.Client() as client:
        response = client.get(f"{BASE_URL}/health")
        # 数据库可能未启动，所以检查状态码是200或503都是可接受的
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "版本" in data


def test_user_register_and_login():
    """测试用户注册和登录流程"""
    # 使用随机邮箱避免冲突
    random_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    
    with httpx.Client() as client:
        # 注册用户
        register_response = client.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={
                "email": random_email,
                "password": "Test@1234",
                "username": "testuser"
            }
        )
        
        # 检查注册是否成功
        assert register_response.status_code == 200
        data = register_response.json()
        assert "id" in data
        assert "email" in data
        assert "token" in data
        
        # 使用注册的用户登录
        login_response = client.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={
                "email": random_email,
                "password": "Test@1234",
                "grant_type": "password"
            }
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "access_token" in login_data
        assert "token_type" in login_data
        
        # 使用token创建会话
        token = login_data["access_token"]
        session_response = client.post(
            f"{BASE_URL}/api/v1/auth/session",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert session_response.status_code == 200
        session_data = session_response.json()
        assert "session_id" in session_data
        assert "name" in session_data
