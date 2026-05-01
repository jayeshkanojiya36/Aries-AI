
import json
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# Global room reference
_current_room = None

def set_room_context(room):
    """Set the current LiveKit room for scanner telemetry."""
    global _current_room
    _current_room = room
    logger.info("Scanner room context initialized")

async def report_scan_progress(percent: int, status_message: str, scan_type: str = "system", file_name: Optional[str] = None):
    """
    Broadcasts scan progress to the frontend UI.
    """
    global _current_room
    if not _current_room:
        return

    try:
        payload = json.dumps({
            "type": "SCAN_PROGRESS",
            "percent": percent,
            "status": status_message,
            "scan_type": scan_type,
            "file_name": file_name
        })
        await _current_room.local_participant.publish_data(payload.encode('utf-8'), reliable=True)
    except Exception as e:
        logger.error(f"Failed to report scan progress: {e}")

async def report_scan_result(result_dict):
    """
    Broadcasts the final scan result to the frontend UI.
    """
    global _current_room
    if not _current_room:
        return

    try:
        # Ensure the type is set correctly for the frontend
        result_dict["type"] = "SCAN_RESULT"
        payload = json.dumps(result_dict)
        await _current_room.local_participant.publish_data(payload.encode('utf-8'), reliable=True)
    except Exception as e:
        logger.error(f"Failed to report scan result: {e}")

async def run_scan_with_progress(cmd, scan_type="system", file_name=None, duration=100):
    """
    Runs a scan while simulating progress over a fixed duration (in seconds).
    If the real scan finishes early, it holds the result until the duration ends.
    If the real scan takes longer, it updates real-time.
    """
    import subprocess
    import os

    # Hide window on Windows
    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    # Step 1: Start the real scan in background
    await report_scan_progress(0, "Initializing scan...", scan_type, file_name)
    proc_task = asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags
    )
    
    proc = await proc_task
    
    # Trackers
    start_time = asyncio.get_event_loop().time()
    scan_complete = False
    stdout, stderr = b"", b""
    
    # Function to collect output while waiting
    async def collect_output():
        nonlocal stdout, stderr, scan_complete
        stdout, stderr = await proc.communicate()
        scan_complete = True

    output_task = asyncio.create_task(collect_output())

    # Step 2: Show progress over 'duration' seconds
    steps = 100
    sleep_interval = duration / steps
    
    for i in range(1, steps + 1):
        # Even if scan is done, we wait for the effect if duration is requested
        await asyncio.sleep(sleep_interval)
        
        # Calculate visual progress - slow down near the end if scan not done
        visual_percent = i
        if i > 95 and not scan_complete:
            visual_percent = 95 # Hold at 95% until real scan is done if it's slow
            
        status = "Analyzing sectors..." if i < 30 else "Deep heuristic scan..." if i < 70 else "Finalizing results..."
        await report_scan_progress(visual_percent, status, scan_type, file_name)

    # Step 3: Wait for real scan if it's still running
    if not scan_complete:
        await report_scan_progress(96, "Waiting for final signatures...", scan_type, file_name)
        await output_task

    await report_scan_progress(100, "Scan Complete", scan_type, file_name)
    
    return stdout.decode('utf-8', errors='ignore'), proc.returncode
