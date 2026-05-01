"""
Calendar Management System for Jarvis
Handles personal events, office events, and Indian holidays
Supports Hinglish date/time parsing
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from livekit.agents import function_tool
import re
from pathlib import Path

# Calendar data storage path
CALENDAR_DATA_PATH = Path(__file__).parent.parent / "calendar_data.json"

# Indian Holidays for 2026 (Asia/Kolkata timezone)
INDIAN_HOLIDAYS_2026 = {
    "2026-01-14": {"title": "Makar Sankranti", "description": "Harvest festival celebrated across India"},
    "2026-01-26": {"title": "Republic Day", "description": "National holiday celebrating the Constitution of India"},
    "2026-03-03": {"title": "Maha Shivaratri", "description": "Hindu festival dedicated to Lord Shiva"},
    "2026-03-06": {"title": "Holi", "description": "Festival of colors"},
    "2026-03-25": {"title": "Good Friday", "description": "Christian holiday"},
    "2026-04-02": {"title": "Ram Navami", "description": "Birthday of Lord Rama"},
    "2026-04-06": {"title": "Mahavir Jayanti", "description": "Jain festival"},
    "2026-04-14": {"title": "Ambedkar Jayanti", "description": "Birthday of Dr. B.R. Ambedkar"},
    "2026-05-01": {"title": "May Day", "description": "International Workers' Day"},
    "2026-05-26": {"title": "Buddha Purnima", "description": "Birthday of Gautama Buddha"},
    "2026-07-07": {"title": "Rath Yatra", "description": "Chariot festival of Lord Jagannath"},
    "2026-08-15": {"title": "Independence Day", "description": "National holiday celebrating India's independence"},
    "2026-08-22": {"title": "Raksha Bandhan", "description": "Festival celebrating brother-sister bond"},
    "2026-08-31": {"title": "Janmashtami", "description": "Birthday of Lord Krishna"},
    "2026-09-11": {"title": "Ganesh Chaturthi", "description": "Birthday of Lord Ganesha"},
    "2026-10-02": {"title": "Gandhi Jayanti", "description": "Birthday of Mahatma Gandhi"},
    "2026-10-15": {"title": "Dussehra", "description": "Victory of good over evil"},
    "2026-10-24": {"title": "Diwali", "description": "Festival of lights"},
    "2026-11-04": {"title": "Guru Nanak Jayanti", "description": "Birthday of Guru Nanak Dev Ji"},
    "2026-12-25": {"title": "Christmas", "description": "Christian holiday celebrating birth of Jesus Christ"},
}


def load_calendar_data() -> Dict[str, Any]:
    """Load calendar data from JSON file"""
    if CALENDAR_DATA_PATH.exists():
        try:
            with open(CALENDAR_DATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading calendar data: {e}")
    
    # Initialize with default structure
    return {
        "personal": {},
        "office": {},
        "holiday": INDIAN_HOLIDAYS_2026
    }


def save_calendar_data(data: Dict[str, Any]) -> bool:
    """Save calendar data to JSON file"""
    try:
        CALENDAR_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CALENDAR_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving calendar data: {e}")
        return False


def parse_hinglish_date(date_str: str) -> Optional[str]:
    """
    Parse Hinglish date expressions to ISO format (YYYY-MM-DD)
    
    Supports:
    - aaj, kal, parso
    - next Monday, iss hafte
    - 14 January, 14-01-2026
    - tomorrow, today, day after tomorrow
    """
    date_str = date_str.lower().strip()
    now = datetime.now()
    
    # Direct date mappings
    if date_str in ["aaj", "today"]:
        return now.strftime("%Y-%m-%d")
    
    if date_str in ["kal", "tomorrow"]:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    if date_str in ["parso", "day after tomorrow"]:
        return (now + timedelta(days=2)).strftime("%Y-%m-%d")
    
    # ISO format (YYYY-MM-DD)
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return date_str
    
    # DD-MM-YYYY or DD/MM/YYYY
    match = re.match(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # DD Month YYYY or DD Month (e.g., "14 January 2026" or "14 January")
    month_names = {
        'january': '01', 'jan': '01',
        'february': '02', 'feb': '02',
        'march': '03', 'mar': '03',
        'april': '04', 'apr': '04',
        'may': '05',
        'june': '06', 'jun': '06',
        'july': '07', 'jul': '07',
        'august': '08', 'aug': '08',
        'september': '09', 'sep': '09',
        'october': '10', 'oct': '10',
        'november': '11', 'nov': '11',
        'december': '12', 'dec': '12'
    }
    
    for month_name, month_num in month_names.items():
        pattern = rf'(\d{{1,2}})\s+{month_name}(?:\s+(\d{{4}}))?'
        match = re.search(pattern, date_str)
        if match:
            day = match.group(1).zfill(2)
            year = match.group(2) if match.group(2) else str(now.year)
            return f"{year}-{month_num}-{day}"
    
    # Next weekday (e.g., "next monday", "monday")
    weekdays = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
        'somwar': 0, 'mangalwar': 1, 'budhwar': 2, 'guruwar': 3,
        'shukrawar': 4, 'shaniwar': 5, 'raviwar': 6
    }
    
    for day_name, day_num in weekdays.items():
        if day_name in date_str:
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0 or 'next' in date_str:
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            return target_date.strftime("%Y-%m-%d")
    
    return None


def parse_hinglish_time(time_str: str) -> Optional[str]:
    """
    Parse Hinglish time expressions to HH:MM format
    
    Supports:
    - 4 baje, 4:30, 4 PM
    - subah 6 baje, shaam 5 baje
    - 16:30, 9:00 AM
    """
    time_str = time_str.lower().strip()
    
    # Handle "baje" (o'clock in Hindi)
    time_str = time_str.replace('baje', '').strip()
    
    # Handle subah (morning) and shaam (evening)
    is_evening = 'shaam' in time_str or 'evening' in time_str
    is_morning = 'subah' in time_str or 'morning' in time_str
    
    time_str = time_str.replace('subah', '').replace('shaam', '').replace('morning', '').replace('evening', '').strip()
    
    # HH:MM format
    match = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if match:
        hour, minute = match.groups()
        return f"{hour.zfill(2)}:{minute}"
    
    # HH AM/PM format
    match = re.match(r'(\d{1,2})\s*(am|pm)', time_str)
    if match:
        hour = int(match.group(1))
        am_pm = match.group(2)
        if am_pm == 'pm' and hour < 12:
            hour += 12
        elif am_pm == 'am' and hour == 12:
            hour = 0
        return f"{str(hour).zfill(2)}:00"
    
    # Just number (e.g., "4" means 4:00)
    match = re.match(r'(\d{1,2})$', time_str)
    if match:
        hour = int(match.group(1))
        
        # Apply context from subah/shaam
        if is_evening and hour < 12:
            hour += 12
        elif is_morning and hour >= 12:
            hour -= 12
        
        return f"{str(hour).zfill(2)}:00"
    
    return None


@function_tool()
async def get_calendar_events(
    start_date: str,
    end_date: str,
    calendar_type: str = "personal"
) -> str:
    """
    Get calendar events within a date range.
    
    Args:
        start_date: Start date in Hinglish (e.g., "aaj", "kal", "14 January") or ISO format
        end_date: End date in Hinglish or ISO format
        calendar_type: Type of calendar - "personal", "office", or "holiday"
    
    Returns:
        Formatted list of events in the date range
    
    Examples:
        - get_calendar_events("aaj", "aaj", "holiday") - Check today's holidays
        - get_calendar_events("kal", "kal", "personal") - Check tomorrow's personal events
        - get_calendar_events("14 January", "26 January", "holiday") - Festivals in range
    """
    try:
        # Parse dates
        start = parse_hinglish_date(start_date)
        end = parse_hinglish_date(end_date)
        
        if not start or not end:
            return f"❌ Date samajh nahi aaya. Please use 'aaj', 'kal', 'parso' ya proper date format."
        
        # Load calendar data
        calendar_data = load_calendar_data()
        
        if calendar_type not in calendar_data:
            return f"❌ Invalid calendar type: {calendar_type}. Use 'personal', 'office', or 'holiday'."
        
        events = calendar_data[calendar_type]
        
        # Filter events in date range
        filtered_events = []
        for event_date, event_info in events.items():
            if start <= event_date <= end:
                filtered_events.append((event_date, event_info))
        
        if not filtered_events:
            if calendar_type == "holiday":
                return f"🗓️ {start} se {end} tak koi festival ya holiday nahi hai."
            else:
                return f"📅 {start} se {end} tak koi {calendar_type} event nahi hai."
        
        # Format response
        result = []
        if calendar_type == "holiday":
            result.append(f"🎉 Festivals/Holidays ({start} se {end}):\n")
        else:
            result.append(f"📅 {calendar_type.title()} Events ({start} se {end}):\n")
        
        for event_date, event_info in sorted(filtered_events):
            date_obj = datetime.strptime(event_date, "%Y-%m-%d")
            day_name = date_obj.strftime("%A")
            formatted_date = date_obj.strftime("%d %B %Y")
            
            title = event_info.get("title", "Untitled")
            time = event_info.get("time", "")
            description = event_info.get("description", "")
            
            result.append(f"📌 {title}")
            result.append(f"   📅 {formatted_date} ({day_name})")
            if time:
                result.append(f"   ⏰ {time}")
            if description:
                result.append(f"   📝 {description}")
            result.append("")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"❌ Error fetching events: {str(e)}"


@function_tool()
async def create_calendar_event(
    title: str,
    date: str,
    time: str = "",
    description: str = "",
    calendar_type: str = "personal"
) -> str:
    """
    Create a new calendar event.
    
    Args:
        title: Event title/name
        date: Date in Hinglish (e.g., "kal", "next Monday", "14 January") or ISO format
        time: Time in Hinglish (e.g., "4 baje", "4:30 PM", "shaam 5 baje") - optional
        description: Event description - optional
        calendar_type: "personal" or "office" (cannot create holidays)
    
    Returns:
        Confirmation message
    
    Examples:
        - create_calendar_event("Doctor Appointment", "kal", "4 baje", "Regular checkup")
        - create_calendar_event("Team Meeting", "next Monday", "10:00 AM", "Sprint planning")
    """
    try:
        # Parse date
        parsed_date = parse_hinglish_date(date)
        if not parsed_date:
            return f"❌ Date samajh nahi aaya: '{date}'. Please use 'aaj', 'kal', ya proper date."
        
        # Parse time if provided
        parsed_time = ""
        if time:
            parsed_time = parse_hinglish_time(time)
            if not parsed_time:
                return f"❌ Time samajh nahi aaya: '{time}'. Please use '4 baje', '4:30 PM', etc."
        
        # Validate calendar type
        if calendar_type not in ["personal", "office"]:
            return f"❌ Calendar type 'personal' ya 'office' hona chahiye. 'holiday' mein add nahi kar sakte."
        
        # Load calendar data
        calendar_data = load_calendar_data()
        
        # Generate event ID
        event_id = f"{parsed_date}_{len(calendar_data[calendar_type])}"
        
        # Create event
        event_info = {
            "title": title,
            "time": parsed_time,
            "description": description,
            "created_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        
        # Add to calendar
        calendar_data[calendar_type][parsed_date] = event_info
        
        # Save
        if save_calendar_data(calendar_data):
            date_obj = datetime.strptime(parsed_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d %B %Y (%A)")
            
            response = [
                f"✅ Event successfully create ho gaya!",
                f"",
                f"📌 {title}",
                f"📅 {formatted_date}"
            ]
            
            if parsed_time:
                response.append(f"⏰ {parsed_time}")
            if description:
                response.append(f"📝 {description}")
            response.append(f"🗂️ Calendar: {calendar_type.title()}")
            
            return "\n".join(response)
        else:
            return "❌ Event save karne mein problem aayi. Please try again."
        
    except Exception as e:
        return f"❌ Error creating event: {str(e)}"


@function_tool()
async def update_calendar_event(
    event_date: str,
    calendar_type: str = "personal",
    new_title: str = "",
    new_time: str = "",
    new_description: str = ""
) -> str:
    """
    Update an existing calendar event.
    
    Args:
        event_date: Date of the event to update (Hinglish or ISO format)
        calendar_type: "personal" or "office"
        new_title: New title (optional, keeps old if not provided)
        new_time: New time (optional, keeps old if not provided)
        new_description: New description (optional, keeps old if not provided)
    
    Returns:
        Confirmation message
    """
    try:
        # Parse date
        parsed_date = parse_hinglish_date(event_date)
        if not parsed_date:
            return f"❌ Date samajh nahi aaya: '{event_date}'"
        
        # Load calendar data
        calendar_data = load_calendar_data()
        
        if calendar_type not in ["personal", "office"]:
            return f"❌ Calendar type 'personal' ya 'office' hona chahiye."
        
        if parsed_date not in calendar_data[calendar_type]:
            return f"❌ {parsed_date} ko koi event nahi mila {calendar_type} calendar mein."
        
        # Get existing event
        event = calendar_data[calendar_type][parsed_date]
        
        # Update fields
        if new_title:
            event["title"] = new_title
        if new_time:
            parsed_time = parse_hinglish_time(new_time)
            if parsed_time:
                event["time"] = parsed_time
        if new_description:
            event["description"] = new_description
        
        event["updated_at"] = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        
        # Save
        if save_calendar_data(calendar_data):
            return f"✅ Event successfully update ho gaya!\n\n📌 {event['title']}\n📅 {parsed_date}"
        else:
            return "❌ Event update karne mein problem aayi."
        
    except Exception as e:
        return f"❌ Error updating event: {str(e)}"


@function_tool()
async def delete_calendar_event(
    event_date: str,
    calendar_type: str = "personal"
) -> str:
    """
    Delete a calendar event.
    
    Args:
        event_date: Date of the event to delete (Hinglish or ISO format)
        calendar_type: "personal" or "office"
    
    Returns:
        Confirmation message
    """
    try:
        # Parse date
        parsed_date = parse_hinglish_date(event_date)
        if not parsed_date:
            return f"❌ Date samajh nahi aaya: '{event_date}'"
        
        # Load calendar data
        calendar_data = load_calendar_data()
        
        if calendar_type not in ["personal", "office"]:
            return f"❌ Calendar type 'personal' ya 'office' hona chahiye."
        
        if parsed_date not in calendar_data[calendar_type]:
            return f"❌ {parsed_date} ko koi event nahi mila {calendar_type} calendar mein."
        
        # Get event title before deleting
        event_title = calendar_data[calendar_type][parsed_date].get("title", "Event")
        
        # Delete event
        del calendar_data[calendar_type][parsed_date]
        
        # Save
        if save_calendar_data(calendar_data):
            return f"✅ Event delete ho gaya!\n\n📌 {event_title}\n📅 {parsed_date}"
        else:
            return "❌ Event delete karne mein problem aayi."
        
    except Exception as e:
        return f"❌ Error deleting event: {str(e)}"
