
import asyncio
import json
import os
from livekit.agents import function_tool
from Tools.scanner_utils import run_scan_with_progress, report_scan_result

@function_tool()
async def scan_system_for_viruses() -> str:
    """
    Performs quick virus scan using Windows Defender silently with progress.
    """
    try:
        # Commands to try
        cmd = [r"C:\Program Files\Windows Defender\MpCmdRun.exe", "-Scan", "-ScanType", "1"]
        alt_cmd = [r"C:\ProgramData\Microsoft\Windows Defender\Platform\4.18.23070.2003-0\MpCmdRun.exe", "-Scan", "-ScanType", "1"]
        
        target_cmd = cmd
        if not os.path.exists(cmd[0]):
            target_cmd = alt_cmd
 
        # Run with 100s simulated duration as requested
        output, returncode = await run_scan_with_progress(target_cmd, scan_type="system", duration=100)
 
        # Parse result
        status = "clean"
        threats = []
        if returncode == 2 or "threat" in output.lower():
            status = "infected"
            for line in output.split('\n'):
                if 'threat' in line.lower() and ':' in line:
                    threats.append(line.split(':', 1)[1].strip())
        
        result_payload = {
            "type": "SCAN_RESULT",
            "scan_type": "system",
            "status": status,
            "threats": threats,
            "message": "System Scan Complete"
        }
 
        # Broadcast to UI
        await report_scan_result(result_payload)
 
        return json.dumps(result_payload)
        
    except Exception as e:
        error_result = {
            "type": "SCAN_RESULT",
            "status": "error",
            "message": f"Scan failed: {str(e)}"
        }
        await report_scan_result(error_result)
        return json.dumps(error_result)