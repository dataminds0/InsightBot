import os
from datetime import datetime
from typing import Dict, List

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import streamlit as st

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = os.getenv("MONGO_DB", "insightbot")

@st.cache_resource(show_spinner=False)
def get_db():
    try:
        client = MongoClient(
            MONGO_URI,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
        )
        db = client[DB_NAME]
        client.admin.command("ping")
        return db
    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.stop()

def _scalarize(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    if isinstance(v, dict):
        for k in ("name", "title", "label", "value", "id", "source", "context", "sentiment", "topic"):
            if v.get(k):
                return str(v[k]).strip()
        return str(v)
    return str(v).strip()

def get_last_page() -> str:
    doc = get_db().app_store.find_one({"key": "last_page"}, {"_id": 0, "value": 1})
    return doc.get("value") if doc else None

def set_last_page(value: str):
    get_db().app_store.update_one({"key": "last_page"}, {"$set": {"value": value}}, upsert=True)

def list_users() -> List[Dict]:
    return list(get_db().users.find({}, {"_id": 0, "password": 0, "password_hash": 0}))

def list_pending_users() -> List[Dict]:
    return list(get_db().users.find({"is_approved": False}, {"_id": 0, "password": 0, "password_hash": 0}))

def find_user_by_username(username: str):
    return get_db().users.find_one({"username": username})

def find_user_by_email(email: str):
    if not email:
        return None
    return get_db().users.find_one({"email": email})

def create_user(user_doc: Dict):
    try:
        get_db().users.insert_one(user_doc)
    except DuplicateKeyError as e:
        raise e

def update_user_by_username(username: str, updates: Dict):
    get_db().users.update_one({"username": username}, {"$set": updates})

def delete_user_by_username(username: str):
    get_db().users.delete_one({"username": username})

def approve_user(username: str):
    get_db().users.update_one({"username": username}, {"$set": {"is_approved": True}})

def reject_user(username: str):
    get_db().users.delete_one({"username": username})


@st.cache_data(show_spinner=False, ttl=10)
def get_articles_df() -> pd.DataFrame:
    rows = list(
        get_db().articles.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "title": 1,
                "content": 1,
                "source": 1,
                "language": 1,
                "sentiment": 1,
                "topic": 1,
                "context": 1,
                "fetched_at": 1,
                "t_total_sec": 1,
                "url": 1,
            },
        )
    )
    if not rows:
        return pd.DataFrame(
            columns=[
                "id",
                "title",
                "content",
                "source",
                "language",
                "sentiment",
                "topic",
                "context",
                "date",
                "t_total_sec",
                "url",
            ]
        )

    df = pd.DataFrame(rows)

    # Normalize date
    if "fetched_at" in df.columns:
        df["date"] = pd.to_datetime(df["fetched_at"], errors="coerce").dt.tz_localize(None)
        df.drop(columns=["fetched_at"], inplace=True, errors="ignore")
    else:
        df["date"] = pd.NaT

    # Ensure all expected columns exist
    for col in ["id", "title", "content", "source", "language", "sentiment", "topic", "context", "t_total_sec", "url"]:
        if col not in df.columns:
            df[col] = None

    # Scalarize mixed fields
    for col in ["language", "sentiment", "source", "topic"]:
        df[col] = df[col].apply(_scalarize)
    df["context"] = df["context"].apply(lambda x: _scalarize(x) or "General")
    df["t_total_sec"] = pd.to_numeric(df["t_total_sec"], errors="coerce")

    return df

def log_event(event_type: str, meta: Dict = None):
    get_db().logs.insert_one(
        {
            "ts": datetime.utcnow(),
            "user": st.session_state.get("username"),
            "event": str(event_type).lower(),
            "meta": meta or {},
        }
    )
