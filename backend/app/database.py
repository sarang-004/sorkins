import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


data_dir = Path(os.environ.get("SORKINS_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
data_dir.mkdir(parents=True, exist_ok=True)
database_url = os.environ.get("SORKINS_DATABASE_URL", f"sqlite:///{data_dir / 'sorkins.db'}")
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
