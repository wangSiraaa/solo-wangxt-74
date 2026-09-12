"""数据库连接。

默认连接 PostgreSQL（见 docker-compose.yml）；本地零配置演示或测试可设：
    DATABASE_URL=sqlite+pysqlite:///./breeding.db
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://breeding:breeding@localhost:5432/breeding",
)

if DATABASE_URL.startswith("sqlite"):
    # 内存/文件 SQLite：测试与本地演示用，单连接共享
    connect_args = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL:
        engine = create_engine(
            DATABASE_URL, connect_args=connect_args, poolclass=StaticPool
        )
    else:
        engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def get_session():
    """FastAPI 依赖：请求级会话。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
