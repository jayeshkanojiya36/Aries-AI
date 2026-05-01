from dotenv import load_dotenv
import warnings
from typing import AsyncIterable

# Suppress deprecation and pydantic warnings for cleaner output
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, room_io, JobContext, utils
from livekit.plugins import (
    noise_cancellation,

    google
)
from google import genai
from google.genai import types as google_types
from google.genai.types import Modality
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION, AGENT_INSTRUCTION_FOR_TOOLS
from mem0 import AsyncMemoryClient
from livekit import rtc
import os
import json
import logging
import asyncio

load_dotenv()

from Tools.reminder import set_reminder, view_reminders, cancel_reminder
from Tools.manage_windows import manage_window,list_windows
# from Tools.search_web import search_web
from Tools.send_whatsapp_message import send_whatsapp_message, reply_to_caller
from Tools.system_power_action import system_power_action
from Tools.type_user_message_auto import type_user_message_auto
from Tools.write_in_notepad import write_in_notepad
from Tools.desktop_control import desktop_control
from Tools.scroll_content import scroll_content
from Tools.code_handler import fix_code_error
from Tools.file_searching import universal_file_opener
from Tools.press_key import press_key,use_smart_clipboard
from Tools.open_app import open_app, smart_app_controller
from Tools.scan_system_for_viruses import scan_system_for_viruses
from Tools.scan_file_for_malware import scan_file_for_malware
from Tools.time_volume_bright import control_screen_brightness,control_system_volume,get_time_info,get_weather,get_system_info_deep
from Tools.multi_task import execute_multi_task
from Tools.generate_ai_image import generate_ai_image
from Tools.code_generator import generate_and_type_code,run_file_in_vscode
from Tools.aries_news import get_latest_news, get_city_news, get_state_news, get_person_info
from Tools.news_provider import get_top_news
from Tools.youtube_videos import play_media, control_youtube, shutdown_youtube
from Tools.screen_short import screen_short
from Tools.pdf_reader import process_document_query
from Tools.send_media_whatsapp import send_media_to_whatsapp
from Tools.calendar_manager import get_calendar_events, create_calendar_event, update_calendar_event, delete_calendar_event
from text_input_handler import handle_text_input
from Tools.create_folder  import create_here
from Tools.read_screen_text import read_screen_text
from Tools.camera_analysis import camera_analysis
from Tools.screen_analyzer import analyze_screen
from Tools.image_analysis import analyze_local_image
from Tools.spotify import (
    open_spotify, spotify_play,spotify_pause,spotify_next,spotify_previous,spotify_play_song,spotify_play_liked
)
from Tools.word_to_pdf  import word_to_pdf,image_to_pdf,excel_to_pdf,ppt_to_pdf,convert_image_format,test_converters
from Tools.excel_data_entery  import create_excel_file,save_excel_changes,delete_all_data,move_left,move_up,enter_data_quick,enter_multiple_data_quick,move_down,move_right,delete_current_cell,go_to_cell,toggle_text_bold,select_row_or_column,sort_excel_data,excel_clipboard_action,calculate_sum

from Tools.send_email import (
    send_email_smart,
    reply_to_last_email,
    read_recent_emails,
    draft_email,
    send_email_direct,
)

from Tools.product_intelligence import compare_product
from Tools.deep_research_agent import (
    search_tavily_web,
    analyze_research_data,
    save_to_notion_db,
    full_research_pipeline,
    get_research_status,
    set_room_context as set_research_room,
)





class Assistant(Agent):
    def __init__(self, chat_ctx=None) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION + "\n\n" + AGENT_INSTRUCTION_FOR_TOOLS,
            llm=google.realtime.RealtimeModel(
                model="gemini-2.5-flash-native-audio-preview-12-2025",
                voice="Aoede",
                temperature=0.7,
                # Video input is enabled via RoomOptions.video_input=True (see entrypoint function)
                # The modalities parameter only accepts AUDIO for Gemini Realtime
                modalities=[Modality.AUDIO],
            ),
            tools=[
                manage_window,
                list_windows,
                # search_web,
                send_whatsapp_message,
                reply_to_caller,
                system_power_action,
                type_user_message_auto,
                write_in_notepad,
                desktop_control,
                scroll_content,
                fix_code_error,
                universal_file_opener,
                press_key,
                use_smart_clipboard,
                open_app,
                smart_app_controller,
                scan_system_for_viruses,
                scan_file_for_malware,
                control_screen_brightness,
                control_system_volume,
                get_time_info,
                get_weather,
                get_system_info_deep,
                execute_multi_task,
                generate_ai_image,
                generate_and_type_code,
                run_file_in_vscode,
                get_latest_news,
                get_city_news,
                get_state_news,
                get_person_info,
                get_top_news,
                play_media,
                control_youtube,
                set_reminder,
                view_reminders,
                cancel_reminder,
                screen_short,
                process_document_query,
                send_media_to_whatsapp,
                get_calendar_events,
                create_calendar_event,
                update_calendar_event,
                delete_calendar_event,
                open_spotify, spotify_play,spotify_pause,spotify_next,spotify_previous,spotify_play_song,spotify_play_liked,
                word_to_pdf,image_to_pdf,excel_to_pdf,ppt_to_pdf,convert_image_format,test_converters,
                create_here,
                read_screen_text,  
                create_excel_file,save_excel_changes,delete_all_data,move_left,move_up,enter_data_quick,enter_multiple_data_quick,move_down,move_right,delete_current_cell,go_to_cell,toggle_text_bold,select_row_or_column,sort_excel_data,excel_clipboard_action,calculate_sum,
                camera_analysis,
                analyze_screen,
                analyze_local_image,
                compare_product,
                # ── Gmail Email Tools (OAuth2) ──────────────────────
                send_email_smart,
                reply_to_last_email,
                read_recent_emails,
                draft_email,
                send_email_direct,
                # ── Deep Research Tools (Tavily + Groq + Notion) ──────────────
                search_tavily_web,
                analyze_research_data,
                save_to_notion_db,
                full_research_pipeline,
                get_research_status,
                
            ],
            chat_ctx=chat_ctx

        )
        
    async def realtime_audio_output_node(
        self, 
        audio: AsyncIterable[rtc.AudioFrame], 
        model_settings
    ) -> AsyncIterable[rtc.AudioFrame]:
        """
        Process audio frames from the Gemini Realtime model to prevent crackling.
        This implements proper audio buffering to handle burst audio delivery.
        """
        stream: utils.audio.AudioByteStream | None = None
        
        async for frame in audio:
            if stream is None:
                # Initialize stream with proper buffering (100ms chunks)
                stream = utils.audio.AudioByteStream(
                    sample_rate=frame.sample_rate,
                    num_channels=frame.num_channels,
                    samples_per_channel=frame.sample_rate // 10,  # 100ms buffer
                )
            
            # Push frame to stream and yield processed frames
            for processed_frame in stream.push(frame.data):
                yield processed_frame
        
        # Flush any remaining audio
        if stream is not None:
            for processed_frame in stream.flush():
                yield processed_frame



async def entrypoint(ctx: agents.JobContext):

    async def periodic_memory_saver(chat_ctx: ChatContext, mem0: AsyncMemoryClient, memory_str: str, user_name: str):
        last_processed_index = 0
        while True:
            await asyncio.sleep(60)
            items = chat_ctx.items
            if last_processed_index >= len(items):
                continue

            messages_formatted = []
            for item in items[last_processed_index:]:
                # Skip items without content attribute (like FunctionCall)
                if not hasattr(item, 'content'):
                    continue
                    
                content_str = ''.join(item.content) if isinstance(item.content, list) else str(item.content)

                if memory_str and memory_str in content_str:
                    continue

                if item.role in ['user', 'assistant']:
                    messages_formatted.append({
                        "role": item.role,
                        "content": content_str.strip()
                    })

            last_processed_index = len(items)

            if messages_formatted:
                logging.info(f"Saving {len(messages_formatted)} new messages to memory periodically...")
                try:
                    await mem0.add(messages_formatted, user_id=user_name)
                    logging.info("Chat context saved to memory successfully.")
                except Exception as e:
                    logging.error(f"Error saving to memory periodically: {e}")

    session = AgentSession(
        
    )

    

    mem0 = AsyncMemoryClient()
    user_name = 'Jayesh'

    # Add timeout to prevent hanging on Mem0 API call
    results = None
    try:
        results = await asyncio.wait_for(
            mem0.get_all(filters={"user_id": user_name}),
            timeout=5.0  # 5 second timeout
        )
    except asyncio.TimeoutError:
        logging.warning(f"Mem0 API call timed out after 5 seconds, continuing without memories")
    except Exception as e:
        logging.error(f"Error fetching memories from Mem0: {e}")
    
    initial_ctx = ChatContext()
    memory_str = ''

    if results and "results" in results and results["results"]:
        memories = [
            {
                "memory": result["memory"],
                "updated_at": result["updated_at"]
            }
            for result in results["results"]
        ]
        memory_str = json.dumps(memories)
        logging.info(f"Memories: {memory_str}")
        initial_ctx.add_message(
            role="assistant",
            content=f"The user's name is {user_name}, and this is relevant context about him: {memory_str}."
        )



    

    await session.start(
        room=ctx.room,
        agent=Assistant(chat_ctx=initial_ctx),
        room_input_options=RoomInputOptions(
            # Standard noise cancellation (NC) is used because we're using Krisp in the frontend
            # When using Krisp in frontend, do NOT use BVC to avoid double-processing
            # NC provides standard echo cancellation and basic noise reduction
            noise_cancellation=noise_cancellation.NC(),
        ),
        room_options=room_io.RoomOptions(
            # Enable live video input for Gemini Realtime model
            # The agent will automatically receive frames from camera or screen sharing
            # Default: 1 frame/sec while user speaks, 1 frame/3sec otherwise
            video_input=True,
            text_input=room_io.TextInputOptions(
                text_input_cb=handle_text_input
            ),
            text_output=room_io.TextOutputOptions(
                sync_transcription=True  # Enable real-time transcription printing
            )
        ),
    )

    await ctx.connect()

    # Set room context for play_media tool and news data broadcasts
    from Tools.youtube_videos import set_room_context as set_youtube_room_context
    from Tools.aries_news import set_room_context as set_news_room_context
    from Tools.news_provider import set_room_context as set_top_news_room_context

    set_youtube_room_context(ctx.room)
    set_news_room_context(ctx.room)
    set_top_news_room_context(ctx.room)
    logging.info("[PLAY_SONG] Room context initialized for media playback")
    logging.info("[NEWS] Room context initialized for news broadcasts")

    # Start the background task to save memory every minute
    memory_task = asyncio.create_task(periodic_memory_saver(initial_ctx, mem0, memory_str, user_name))

    try:
        logging.info("[AUDIO] Generating initial greeting...")
        await asyncio.wait_for(
            session.generate_reply(
                instructions=SESSION_INSTRUCTION,
            ),
            timeout=10.0  # 10 second timeout for initial greeting
        )
        logging.info("[OK] Initial greeting generated successfully")
    except asyncio.TimeoutError:
        logging.warning("[WARN] Initial greeting timed out, continuing without it...")
    except Exception as e:
        logging.error(f"[ERROR] Error generating initial reply: {e}")
        logging.info("Continuing without initial greeting...")

    # Note: Shutdown callback removed to fix AssertionError in LiveKit worker lifecycle
    # The async shutdown_hook cannot be properly called from add_shutdown_callback
    # Memory saving is handled by the session's built-in cleanup

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))