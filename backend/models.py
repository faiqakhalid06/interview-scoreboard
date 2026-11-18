from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "admin" or "judge"

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)

class Criterion(Base):
    __tablename__ = "criteria"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    weight = Column(Float, nullable=False)

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    criterion_id = Column(Integer, ForeignKey("criteria.id"), nullable=False)
    marks = Column(Integer, nullable=False)

    # One judge, one mark per criterion per candidate (the "score once" rule)
    __table_args__ = (UniqueConstraint("judge_id", "candidate_id", "criterion_id"),)