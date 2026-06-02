from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    if "pooler.supabase.com" in database_url or ":6543" in database_url:
        return {"prepare_threshold": None}
    return {}


settings = get_settings()
def _engine_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


engine = create_engine(
    _engine_url(settings.database_url),
    connect_args=_connect_args(settings.database_url),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    return Config(str(root / "alembic.ini"))


def run_migrations() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    has_legacy_schema = bool({"documents", "eval_cases", "eval_runs", "eval_results"} & tables)
    has_version_table = "alembic_version" in tables
    config = _alembic_config()

    if has_legacy_schema and not has_version_table:
        ensure_schema()
        command.stamp(config, "head")
        return

    command.upgrade(config, "head")


def ensure_schema() -> None:
    inspector = inspect(engine)
    if "eval_runs" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("eval_runs")}
        run_columns = {
            "provider": "VARCHAR DEFAULT 'mock' NOT NULL",
            "model": "VARCHAR DEFAULT 'mock-deterministic' NOT NULL",
            "judge_enabled": "BOOLEAN DEFAULT false NOT NULL",
            "status": "VARCHAR DEFAULT 'completed' NOT NULL",
        }
        with engine.begin() as conn:
            for name, ddl in run_columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE eval_runs ADD COLUMN {name} {ddl}"))

    inspector = inspect(engine)
    if "eval_cases" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("eval_cases")}
        case_columns = {
            "acceptable_actions_json": "TEXT DEFAULT '[]' NOT NULL",
            "context_json": "TEXT DEFAULT '{}' NOT NULL",
            "expected_decision_json": "TEXT DEFAULT '{}' NOT NULL",
        }
        with engine.begin() as conn:
            for name, ddl in case_columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE eval_cases ADD COLUMN {name} {ddl}"))

    inspector = inspect(engine)
    if "eval_results" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("eval_results")}
        result_columns = {
            "fact_recall": "FLOAT DEFAULT 0 NOT NULL",
            "fact_precision": "FLOAT DEFAULT 0 NOT NULL",
            "action_input_score": "FLOAT DEFAULT 0 NOT NULL",
            "retrieval_hit": "FLOAT DEFAULT 0 NOT NULL",
            "groundedness": "FLOAT DEFAULT 0 NOT NULL",
            "schema_valid": "BOOLEAN DEFAULT true NOT NULL",
            "judge_score": "FLOAT",
            "slot_valid": "BOOLEAN DEFAULT true NOT NULL",
            "preference_score": "FLOAT DEFAULT 1 NOT NULL",
            "timezone_correct": "BOOLEAN DEFAULT true NOT NULL",
            "proposed_slot": "TEXT DEFAULT '' NOT NULL",
            "unsupported_claims_json": "TEXT DEFAULT '[]' NOT NULL",
            "failure_mode": "VARCHAR DEFAULT 'none' NOT NULL",
            "failure_explanation": "TEXT DEFAULT '' NOT NULL",
            "trace_json": "TEXT DEFAULT '{}' NOT NULL",
        }
        with engine.begin() as conn:
            for name, ddl in result_columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE eval_results ADD COLUMN {name} {ddl}"))
