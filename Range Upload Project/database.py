# ============================================================
# SECTION 1 — IMPORTS + BASE + ENGINE
# ============================================================

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# -------------------------
# Database URL
# -------------------------
DATABASE_URL = "sqlite:///./soldier_data.db"

# -------------------------
# Engine
# -------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # required for SQLite
)
# ============================================================
# SECTION 2 — SESSION FACTORY
# ============================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)
# ============================================================
# SECTION 3 — CREATE TABLES
# ============================================================

def init_db():
    Base.metadata.create_all(bind=engine)
