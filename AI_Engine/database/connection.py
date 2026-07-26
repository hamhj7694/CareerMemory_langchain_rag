"""SQLAlchemy 엔진과 요청별 데이터베이스 세션을 관리한다."""

from __future__ import annotations

# 1. Python 기본 기능
# 환경 변수와 SQLite 파일 경로를 안전하게 준비하는 데 사용한다.
import os
from collections.abc import Generator
from pathlib import Path

# 2. SQLAlchemy 연결 기능
# Engine은 DB 연결 방법을 보관하고 Session은 한 API 요청의 DB 작업 범위를 관리한다.
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# 3. 프로젝트 환경 변수
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "career_memory.db"
DEFAULT_DATABASE_URL = (
    f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    DEFAULT_DATABASE_URL,
).strip()


# 4. SQLAlchemy 모델의 공통 부모
# models.py의 모든 테이블 클래스는 이 Base를 상속한다.
class Base(DeclarativeBase):
    pass


# 5. 데이터베이스 Engine 생성
# SQLite는 같은 연결을 여러 FastAPI 요청에서 사용할 수 있도록 별도 옵션이 필요하다.
if DATABASE_URL.startswith("sqlite"):
    DEFAULT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}
else:
    connect_args = {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# 6. 테이블 초기화
# 서버 시작 시 아직 없는 테이블만 생성한다. 기존 데이터와 테이블은 삭제하지 않는다.
def initialize_database() -> None:
    """등록된 SQLAlchemy 모델을 기준으로 누락된 테이블을 생성한다."""

    # 모델 모듈을 불러와야 Base가 생성할 테이블 목록을 알 수 있다.
    from AI_Engine.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # create_all은 기존 SQLite 테이블에 새 컬럼을 추가하지 않는다.
    # 인증 기능 도입 전에 만들어진 로컬 DB에는 user_id를 안전하게 한 번 추가한다.
    if DATABASE_URL.startswith("sqlite"):
        conversation_columns = {
            column["name"]
            for column in inspect(engine).get_columns("conversations")
        }
        if "user_id" not in conversation_columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE conversations "
                        "ADD COLUMN user_id VARCHAR(50)"
                    )
                )

        conversation_columns = {
            column["name"]
            for column in inspect(engine).get_columns("conversations")
        }
        missing_conversation_columns = {
            "last_successful_extraction_sequence": "INTEGER NOT NULL DEFAULT 0",
            "last_extraction_at": "DATETIME",
        }
        with engine.begin() as connection:
            for column_name, column_type in missing_conversation_columns.items():
                if column_name not in conversation_columns:
                    connection.execute(text(
                        f"ALTER TABLE conversations ADD COLUMN {column_name} {column_type}"
                    ))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_conversations_user_id "
                    "ON conversations (user_id)"
                )
            )

        user_columns = {
            column["name"]
            for column in inspect(engine).get_columns("users")
        }
        missing_user_columns = {
            "username": "VARCHAR(30)",
            "recovery_question": "VARCHAR(50)",
            "recovery_answer_hash": "VARCHAR(500)",
            "recovery_failed_attempts": "INTEGER NOT NULL DEFAULT 0",
            "recovery_locked_until": "DATETIME",
        }
        with engine.begin() as connection:
            for column_name, column_type in missing_user_columns.items():
                if column_name not in user_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE users ADD COLUMN "
                            f"{column_name} {column_type}"
                        )
                    )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "ix_users_username ON users (username)"
                )
            )


# 7. 요청별 DB 세션
# API 처리 후 성공·실패와 관계없이 연결을 닫아 연결 누수를 막는다.
def get_database_session() -> Generator[Session, None, None]:
    """FastAPI 요청 하나에서 사용할 DB 세션을 제공한다."""

    database_session = SessionLocal()
    try:
        yield database_session
    finally:
        database_session.close()


__all__ = [
    "Base",
    "DATABASE_URL",
    "DEFAULT_DATABASE_URL",
    "SessionLocal",
    "engine",
    "get_database_session",
    "initialize_database",
]
