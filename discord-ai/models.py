from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from database import Base, engine

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, index=True)  # Discord message ID (string)
    user = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    channel_id = Column(String, nullable=False)
    processed = Column(Integer, default=0)  # 0: Unprocessed, 1: Processed by AI background task

class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    content = Column(Text, nullable=False)
    status = Column(String, default="Pending")  # Pending, Approved, Rejected

def init_db():
    Base.metadata.create_all(bind=engine)
