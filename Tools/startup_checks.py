import asyncio
import sqlite3
import json
import re
from datetime import datetime, date, timedelta
from typing import Optional
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Assuming jarvis_memory is at project root.
# This file is in Tools/ so we go up one level.
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jarvis_memory", "chat_history.db")
TABLE_NAME = "chat_messages"

async def get_today_reminder_message_from_db() -> Optional[str]:
    """Get today's reminders from the database"""
    today = datetime.now().date()
    try:
        print(f"🔍 Checking reminders for {today}")
        
        if not os.path.exists(DB_PATH):
            logger.warning(f"Database not found at {DB_PATH}")
            return None

        def db_operation():
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute(f"SELECT role, content FROM {TABLE_NAME} ORDER BY created_at ASC")
            rows = cursor.fetchall()
            conn.close()
            return rows
        
        rows = await asyncio.create_task(asyncio.to_thread(db_operation))
        reminders = []

        for role, content_json in rows:
            if role != "user":
                continue

            try:
                # content_json might be a string or json list depending on storage
                # The original code did json.loads(content_json).
                content_items = json.loads(content_json)
                if isinstance(content_items, str):
                    content_items = [content_items]
                
                for item in content_items:
                    item_lower = item.lower()

                    if "remind" in item_lower or "remember" in item_lower or "याद दिला" in item_lower:
                        reminder_date = extract_date_from_text(item_lower)
                        if reminder_date and reminder_date == today:
                            reminders.append(item)
            except Exception as e:
                # print(f"⚠️ Error parsing content: {e}") 
                continue

        if reminders:
            combined = "\n".join(f"🔔 {r}" for r in reminders)
            return f"🧠 सर, आज आपको याद है न — {combined}"

        return None

    except Exception as e:
        print(f"❌ Error while checking reminders: {e}")
        return None

def extract_date_from_text(text: str) -> Optional[date]:
    """Extract date from text"""
    today = datetime.now().date()

    date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if date_match:
        try:
            return datetime.strptime(date_match.group(), "%Y-%m-%d").date()
        except:
            return None

    if "आज" in text:
        return today
    elif "कल" in text:
        return today + timedelta(days=1)

    return None
