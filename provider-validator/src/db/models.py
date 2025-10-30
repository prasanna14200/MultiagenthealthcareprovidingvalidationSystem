# src/db/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import declarative_base
from datetime import datetime
import os

Base = declarative_base()

class Provider(Base):
    __tablename__ = "providers"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    phone = Column(String)
    email = Column(String)
    address = Column(String)
    specialty = Column(String)
    confidence = Column(String)

class OutreachLog(Base):
    __tablename__ = "outreach_logs"
    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer)
    subject = Column(Text)
    body = Column(Text)
    recipient_email = Column(String)
    send_status = Column(String)
    send_time = Column(String)
    provider_response_id = Column(String)
    task_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
