
import re
from typing import Dict, Union, Optional

def parse_voice_command(text: str) -> Dict[str, Union[str, int, None]]:
    """
    Maps natural language voice commands to structured YouTube actions.
    
    Example mappings:
    - "play arijit singh" -> {action: "play", value: "arijit singh"}
    - "skip 30 seconds" -> {action: "skip", value: 30}
    - "go to 2 mins 15 secs" -> {action: "seek", value: 135}
    - "volume up" -> {action: "vol_up"}
    """
    text = text.lower().strip()
    
    # Check for direct actions
    if "pause" in text:
        return {"action": "pause", "value": None}
    
    elif "resume" in text or "start video" in text or "continue" in text:
        return {"action": "resume", "value": None}
        
    elif "next" in text or "skip song" in text:
        return {"action": "next", "value": None}
        
    elif "previous" in text or "back" in text:
        return {"action": "prev", "value": None}
        
    elif "mute" in text:
        return {"action": "mute", "value": None}
        
    elif "unmute" in text:
        return {"action": "unmute", "value": None}
        
    elif "full screen" in text or "maximize" in text:
        return {"action": "fullscreen", "value": None}
        
    elif "minimize" in text or "small screen" in text:
        return {"action": "minimize", "value": None}
        
    elif "skip ad" in text:
        return {"action": "skip_ad", "value": None} # Although automatic, user might force it
        
    elif "volume up" in text or "increase volume" in text:
        return {"action": "vol_up", "value": None}
        
    elif "volume down" in text or "decrease volume" in text:
        return {"action": "vol_down", "value": None}

    # Timestamp regex (e.g., "go to 2 minutes 30 seconds")
    seek_pattern = re.search(r'go to (\d+)\s*(?:minutes?|mins?)?\s*(\d+)?\s*(?:seconds?|secs?)?', text)
    if seek_pattern:
        minutes = int(seek_pattern.group(1)) if seek_pattern.group(1) else 0
        seconds = int(seek_pattern.group(2)) if seek_pattern.group(2) else 0
        total_seconds = (minutes * 60) + seconds
        return {"action": "seek", "value": total_seconds}
        
    # Relative skip regex (e.g., "skip 30 seconds")
    skip_pattern = re.search(r'skip (\d+)\s*(?:seconds?|secs?)', text)
    if skip_pattern:
        seconds = int(skip_pattern.group(1))
        return {"action": "skip", "value": seconds}
        
    # Play command (fallback)
    if "play" in text:
        query = text.replace("play", "", 1).replace("on youtube", "").strip()
        if query:
            return {"action": "play", "value": query}
            
    return {"action": "unknown", "value": None}
