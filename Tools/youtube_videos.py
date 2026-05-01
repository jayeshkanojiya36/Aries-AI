
import asyncio
import logging
from typing import Literal, Optional
from livekit.agents import function_tool
from Tools.youtube_controller import get_controller
from Tools.youtube_intent_parser import parse_voice_command

logger = logging.getLogger(__name__)

# Global room reference (kept for compatibility, though we are now controlling local browser)
_current_room = None

def set_room_context(room):
    """Set the current LiveKit room (kept for compatibility)"""
    global _current_room
    _current_room = room
    logger.info(f"Room context set (Hybrid mode: Local Browser + DataChannel)")

@function_tool()
async def play_media(media_name: str, media_type: Literal["song", "video"] = "song") -> str:
    """
    Plays a video or song on YouTube using the local browser controller.
    
    Args:
        media_name: The name of the song or video to play.
        media_type: Type of media (default: "song").
    """
    try:
        logger.info(f"Playing: {media_name}")
        
        # Broadcast to frontend if connected
        global _current_room
        if _current_room:
            try:
                import json
                # Create search URL if not a direct link
                video_url = media_name
                if "youtube.com" not in media_name and "youtu.be" not in media_name:
                    video_url = f"https://www.youtube.com/results?search_query={media_name.replace(' ', '+')}"
                
                payload = json.dumps({
                    "type": "PLAY_SONG",
                    "title": media_name,
                    "url": video_url,
                    "video_id": None
                })
                await _current_room.local_participant.publish_data(payload.encode('utf-8'), reliable=True)
                logger.info(f"Broadcasted PLAY_SONG: {media_name}")
            except Exception as e:
                logger.error(f"Failed to broadcast to room: {e}")

        controller = await get_controller()
        await controller.play_video(media_name)
        return f"Playing {media_name} on YouTube."
    except Exception as e:
        logger.error(f"Error playing media: {e}")
        return f"Failed to play media: {e}"

@function_tool()
async def control_youtube(command: str) -> str:
    """
    Controls the YouTube playback with voice commands.
    Supports: pause, resume, next, previous, mute, unmute, fullscreen, minimize, skip ad, volume up/down.
    
    Args:
        command: The voice command text (e.g., "pause video", "skip ad", "volume up").
    """
    try:
        parsed = parse_voice_command(command)
        action = parsed["action"]
        value = parsed["value"]
        
        if action == "unknown":
            return f"Sorry, I didn't understand the command: {command}"
            
        controller = await get_controller()
        
        if action == "play" and value:
            await controller.play_video(str(value))
            return f"Playing {value}"
            
        await controller.control(action, value)
        return f"Executed YouTube command: {action}"
        
    except Exception as e:
        logger.error(f"Error controlling YouTube: {e}")
        return f"Failed to execute command: {e}"

async def shutdown_youtube():
    """Closes the YouTube controller cleanly."""
    try:
        controller = await get_controller()
        await controller.close()
        logger.info("YouTube Controller closed.")
    except Exception as e:
        logger.error(f"Error closing YouTube controller: {e}")
