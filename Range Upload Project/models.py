# ============================================================
# SECTION 1 — IMPORTS + BASE
# ============================================================

from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
# ============================================================
# SECTION 2 — USER MODEL
# ============================================================

class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # soldier / nco / officer / admin
    role = Column(String, nullable=False)

    # supervisor_id:
    # - soldier → NCO
    # - NCO → officer
    # - officer → admin (optional)
    supervisor_id = Column(String, ForeignKey("users.user_id"), nullable=True)

    # relationships
    supervisor = relationship("User", remote_side=[user_id])
# ============================================================
# SECTION 3 — RANGE CARD MODEL
# ============================================================

class RangeCard(Base):
    __tablename__ = "rangecards"

    file_id = Column(String, primary_key=True, index=True)

    soldier_id = Column(String, ForeignKey("users.user_id"), nullable=True)

    filename = Column(String, nullable=False)
    description = Column(String, nullable=False)

    # pending / approved / rejected
    status = Column(String, nullable=True)

    uploaded_at = Column(String, nullable=True)

    # legacy qualification term:
    # Unqualified / Marksman / Sharpshooter / Expert
    legacy_term = Column(String, nullable=True)

    soldier = relationship("User")
