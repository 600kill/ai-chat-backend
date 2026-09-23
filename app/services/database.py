"""
应用程序数据库服务文件
"""
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool
from sqlmodel import Session, create_engine, select
from app.core.config import Environment, settings
from app.core.logging import logger
from app.models.session import Session as ChatSession
from app.models.user import User

class DatabaseService:
    """
    数据库操作服务类
    处理用户、会话、消息的所有数据库操作
    使用 SQLModel 完成 ORM 操作，并维护连接池
    """
    def __init__(self):
        """初始化数据库服务，创建连接池与数据库引擎"""
        try:
            # 读取配置：连接池大小
            pool_size = settings.POSTGRES_POOL_SIZE
            # 读取配置：最大溢出连接数
            max_overflow = settings.POSTGRES_MAX_OVERFLOW

            # 拼接 PostgreSQL 连接字符串
            connection_url = (
                f"postgresql+psycopg2://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
                f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )

            # 创建数据库引擎（带连接池配置）
            self.engine = create_engine(
                connection_url,
                pool_pre_ping=True,        # 使用前检查连接有效性
                poolclass=QueuePool,       # 队列连接池
                pool_size=pool_size,       # 常驻连接数
                max_overflow=max_overflow, # 允许的临时连接数
                pool_timeout=30,           # 获取连接超时时间
                pool_recycle=1800,         # 30分钟自动回收连接
            )

            # 记录初始化成功日志
            logger.info("database_initialized",
                        environment=settings.ENVIRONMENT.value,
                        pool_size=pool_size,
                        max_overflow=max_overflow)

        except SQLAlchemyError as e:
            # 初始化失败，记录错误
            logger.error("database_initialization_error", error=str(e), environment=settings.ENVIRONMENT.value)
            # 非生产环境直接抛出异常，便于调试
            if settings.ENVIRONMENT != Environment.PRODUCTION:
                raise

    async def create_user(self, email: str, password: str, username: str | None = None) -> User:
        """创建新用户"""
        # 创建数据库会话
        with Session(self.engine) as session:
            # 构造用户对象
            user = User(email=email, hashed_password=password, username=username)
            # 添加到会话
            session.add(user)
            # 提交事务
            session.commit()
            # 刷新对象（获取数据库生成字段）
            session.refresh(user)
            logger.info("user_created", email=email)
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """根据用户ID查询用户"""
        with Session(self.engine) as session:
            # 按主键查询
            user = session.get(User, user_id)
            return user

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查询用户"""
        with Session(self.engine) as session:
            # 构造查询语句
            statement = select(User).where(User.email == email)
            # 执行查询，取第一条
            user = session.exec(statement).first()
            return user

    async def delete_user_by_email(self, email: str) -> bool:
        """根据邮箱删除用户"""
        with Session(self.engine) as session:
            user = session.exec(select(User).where(User.email == email)).first()
            if not user:
                return False
            # 删除用户
            session.delete(user)
            session.commit()
            logger.info("user_deleted", email=email)
            return True

    async def create_session(self, session_id: str, user_id: int, name: str = "", username: str | None = None) -> ChatSession:
        """创建聊天会话"""
        with Session(self.engine) as session:
            chat_session = ChatSession(id=session_id, user_id=user_id, name=name, username=username)
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("session_created", session_id=session_id, user_id=user_id, name=name)
            return chat_session

    async def delete_session(self, session_id: str) -> bool:
        """根据会话ID删除会话"""
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if not chat_session:
                return False
            session.delete(chat_session)
            session.commit()
            logger.info("session_deleted", session_id=session_id)
            return True

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """根据会话ID查询会话"""
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            return chat_session

    async def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        """查询用户的所有会话，按创建时间排序"""
        with Session(self.engine) as session:
            statement = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at)
            sessions = session.exec(statement).all()
            return sessions

    async def update_session_name(self, session_id: str, name: str) -> ChatSession:
        """更新会话名称"""
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if not chat_session:
                raise HTTPException(status_code=404, detail="会话不存在")
            # 修改会话名称
            chat_session.name = name
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("session_name_updated", session_id=session_id, name=name)
            return chat_session

    def get_session_maker(self):
        """获取数据库会话构造器，用于手动创建会话"""
        return lambda: Session(self.engine)

    async def health_check(self) -> bool:
        """数据库健康检查，测试连接是否正常"""
        try:
            with Session(self.engine) as session:
                # 执行简单语句验证连通性
                session.exec(select(1)).first()
                return True
        except Exception as e:
            logger.error("database_health_check_failed", error=str(e))
            return False

    # ==================== 管理员方法 ====================
    async def get_all_users(self) -> List[User]:
        """获取所有用户（管理员用）"""
        with Session(self.engine) as session:
            statement = select(User).order_by(User.created_at)
            users = session.exec(statement).all()
            return users

    async def delete_user(self, user_id: int) -> bool:
        """根据用户ID删除用户（管理员用）"""
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            if not user:
                return False
            session.delete(user)
            session.commit()
            logger.info("user_deleted_by_id", user_id=user_id)
            return True

    async def get_all_sessions(self) -> List[ChatSession]:
        """获取所有会话（管理员用）"""
        with Session(self.engine) as session:
            statement = select(ChatSession).order_by(ChatSession.created_at)
            sessions = session.exec(statement).all()
            return sessions

# 全局单例：整个应用共用一个数据库服务实例
database_service = DatabaseService()