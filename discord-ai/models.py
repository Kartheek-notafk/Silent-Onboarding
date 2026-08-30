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
    priority = Column(String, default="Medium")  # High, Medium, Low
    target_section = Column(String, nullable=True)  # Section/Topic in docs to update
    proposed_change = Column(Text, nullable=True)  # Specific doc update content
    admin_notes = Column(Text, nullable=True)  # Admin suggestions/corrections

class KeywordTracker(Base):
    __tablename__ = "keyword_tracker"

    keyword = Column(String, primary_key=True, index=True)
    count = Column(Integer, default=1)
    last_updated = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
