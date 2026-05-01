"""
Text Input Handler for Aries AI
Handles text messages from the frontend terminal
"""

import logging
from livekit.agents import AgentSession, room_io


async def handle_text_input(session: AgentSession, event: room_io.TextInputEvent) -> None:
    """
    Handle text input from the frontend terminal
    
    Args:
        session: The AgentSession instance
        event: The text input event containing the message
    """
    import json
    
    message = event.text
    logging.info(f"📝 Received text input: {message}")
    
    # Handle JSON commands from frontend (e.g., file scan requests)
    try:
        cmd = json.loads(message)
        
        # Handle file scan command
        if cmd.get('type') == 'SCAN_FILE':
            file_path = cmd.get('filePath')
            logging.info(f"🔍 File scan requested: {file_path}")
            
            # Import and execute scan
            from Tools.scan_file_for_malware import scan_file_for_malware
            result = await scan_file_for_malware(file_path)
            
            # Send result back via DataChannel
            response = json.dumps({
                "type": "SCAN_RESULT",
                "result": result
            })
            
            # Publish via room data channel
            encoder = TextEncoder()
            await session._agent._room.local_participant.publish_data(
                encoder.encode(response),
                reliable=True
            )
            
            logging.info(f"✅ Scan result sent to frontend")
            return
            
    except json.JSONDecodeError:
        pass  # Not JSON, continue normal processing
    
    # Handle special commands
    if message.startswith("/"):
        if message == "/help":
            session.say("Available commands: /help, /status, /clear")
            return
        elif message == "/status":
            session.say("Aries is running normally. Vision and voice systems are active.")
            return
        elif message == "/clear":
            session.say("Chat cleared")
            return
        else:
            session.say(f"Unknown command: {message}")
            return
    
    # Apply basic filtering (optional)
    forbidden_words = ["spam", "test123"]
    if any(word in message.lower() for word in forbidden_words):
        session.say("I can't respond to that type of message.")
        return
    
    # Default behavior: process the text input
    logging.info(f"Processing text input as user message: {message}")
    session.interrupt()  # Stop current speech if any
    session.generate_reply(user_input=message)
