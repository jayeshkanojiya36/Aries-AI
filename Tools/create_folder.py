"""
Folder/File Creation Tool for Jarvis AI
Creates folders and files in the active File Explorer window location
"""

import os
import subprocess
import asyncio
from datetime import datetime
from livekit.agents import function_tool
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@function_tool()
async def create_here(item_name: str, item_type: str = "folder") -> str:
    """
    Creates a folder or file in ACTIVE File Explorer window location.
    Uses PowerShell to get exact current path.
    
    Args:
        item_name: Name of folder/file to create (supports Hindi/English)
        item_type: 'folder' or 'file' (default: 'folder')
        
    Returns: 
        Success/error message with full path
        
    Examples:
        - create_here("MyFolder", "folder")
        - create_here("notes", "file")
        - create_here("प्रोजेक्ट", "folder")  # Hindi names supported
    """
    logger.info(f"[CREATE_HERE] Starting - item_name='{item_name}', item_type='{item_type}'")
    
    try:
        # Step 1: Get active File Explorer path
        logger.info("[CREATE_HERE] Getting File Explorer path...")
        explorer_path = await _get_active_explorer_path()
        
        if not explorer_path:
            msg = "❌ No File Explorer window is open. Please open File Explorer first and try again."
            logger.error(f"[CREATE_HERE] {msg}")
            return msg
        
        logger.info(f"[CREATE_HERE] Explorer path found: {explorer_path}")
        
        if not os.path.exists(explorer_path):
            msg = f"❌ Path doesn't exist: {explorer_path}"
            logger.error(f"[CREATE_HERE] {msg}")
            return msg
        
        # Step 2: Sanitize and prepare item name
        item_name = item_name.strip()
        
        if not item_name:
            return "❌ Item name cannot be empty"
        
        # Simple translation for common Hindi words (no external API calls)
        item_name = _translate_simple(item_name)
        logger.info(f"[CREATE_HERE] Sanitized name: '{item_name}'")
        
        # Remove invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            item_name = item_name.replace(char, '_')
        
        full_path = os.path.join(explorer_path, item_name)
        logger.info(f"[CREATE_HERE] Target path: {full_path}")
        
        # Step 3: Create folder or file
        if item_type.lower() in ['folder', 'dir', 'directory']:
            return await _create_folder(item_name, full_path, explorer_path)
        elif item_type.lower() in ['file', 'txt', 'text']:
            return await _create_file(item_name, full_path, explorer_path)
        else:
            return f"❌ Invalid type '{item_type}'. Use 'folder' or 'file' only."
        
    except PermissionError as e:
        msg = f"❌ Permission denied! Cannot create in this location. Try a different folder."
        logger.error(f"[CREATE_HERE] {msg} - {e}")
        return msg
    except Exception as e:
        msg = f"❌ Error: {str(e)}"
        logger.error(f"[CREATE_HERE] Unexpected error: {e}", exc_info=True)
        return msg


async def _create_folder(item_name: str, full_path: str, explorer_path: str) -> str:
    """Create a folder at the specified path"""
    try:
        if os.path.exists(full_path):
            logger.info(f"[CREATE_FOLDER] Folder already exists: {full_path}")
            return f"✅ Folder '{item_name}' already exists at:\n📍 {full_path}"
        
        logger.info(f"[CREATE_FOLDER] Creating folder: {full_path}")
        os.makedirs(full_path, exist_ok=True)
        
        # Verify creation
        if os.path.exists(full_path):
            logger.info(f"[CREATE_FOLDER] ✅ Folder created successfully")
            await _refresh_explorer()
            return f"✅ Folder '{item_name}' created successfully!\n📍 Location: {full_path}\n📁 In: {explorer_path}"
        else:
            return f"❌ Failed to create folder (verification failed)"
            
    except Exception as e:
        logger.error(f"[CREATE_FOLDER] Error: {e}")
        raise


async def _create_file(item_name: str, full_path: str, explorer_path: str) -> str:
    """Create a text file at the specified path"""
    try:
        # Add .txt extension if not present
        if not item_name.lower().endswith('.txt'):
            item_name = item_name + '.txt'
            full_path = os.path.join(explorer_path, item_name)
        
        if os.path.exists(full_path):
            logger.info(f"[CREATE_FILE] File already exists: {full_path}")
            return f"✅ File '{item_name}' already exists at:\n📍 {full_path}"
        
        logger.info(f"[CREATE_FILE] Creating file: {full_path}")
        with open(full_path, 'w', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"Created by Jarvis AI\n")
            f.write(f"Date: {timestamp}\n")
            f.write(f"\n")
        
        # Verify creation
        if os.path.exists(full_path):
            logger.info(f"[CREATE_FILE] ✅ File created successfully")
            await _refresh_explorer()
            return f"✅ File '{item_name}' created successfully!\n📍 Location: {full_path}\n📁 In: {explorer_path}"
        else:
            return f"❌ Failed to create file (verification failed)"
            
    except Exception as e:
        logger.error(f"[CREATE_FILE] Error: {e}")
        raise


async def _get_active_explorer_path() -> str:
    """
    Get the path of the active File Explorer window using PowerShell.
    Returns the path as a string, or None if no explorer window is found.
    """
    logger.info("[EXPLORER_PATH] Detecting active File Explorer window...")
    
    try:
        # PowerShell script to get active File Explorer path
        # This is the most reliable method on Windows
        ps_script = """
        try {
            $shell = New-Object -ComObject Shell.Application
            $windows = $shell.Windows()
            
            # Try to get the first File Explorer window
            foreach ($window in $windows) {
                try {
                    if ($window.FullName -like "*explorer.exe*") {
                        $path = $window.Document.Folder.Self.Path
                        if ($path -and (Test-Path $path)) {
                            Write-Output $path
                            exit 0
                        }
                    }
                } catch {}
            }
            
            # If no window found, exit with error
            exit 1
        } catch {
            exit 1
        }
        """
        
        logger.info("[EXPLORER_PATH] Running PowerShell detection...")
        
        # Run PowerShell with timeout
        result = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-Command', ps_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            ),
            timeout=5.0
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0 and stdout:
            path = stdout.decode('utf-8').strip()
            if path and os.path.exists(path):
                logger.info(f"[EXPLORER_PATH] ✅ Found: {path}")
                return path
            else:
                logger.warning(f"[EXPLORER_PATH] Path invalid: {path}")
        else:
            logger.warning(f"[EXPLORER_PATH] PowerShell failed (code {result.returncode})")
            if stderr:
                logger.warning(f"[EXPLORER_PATH] Stderr: {stderr.decode('utf-8').strip()}")
        
        # Fallback: Try simpler method
        logger.info("[EXPLORER_PATH] Trying fallback method...")
        fallback_result = await _get_explorer_path_fallback()
        if fallback_result:
            return fallback_result
        
        logger.error("[EXPLORER_PATH] ❌ No File Explorer window found")
        return None
        
    except asyncio.TimeoutError:
        logger.error("[EXPLORER_PATH] ❌ PowerShell timeout")
        return None
    except Exception as e:
        logger.error(f"[EXPLORER_PATH] ❌ Error: {e}", exc_info=True)
        return None


async def _get_explorer_path_fallback() -> str:
    """Fallback method to get File Explorer path"""
    try:
        ps_script = """
        $shell = New-Object -ComObject Shell.Application
        $window = $shell.Windows() | Where-Object { $_.LocationURL -like 'file:*' } | Select-Object -First 1
        if ($window) { 
            $path = $window.Document.Folder.Self.Path
            if ($path -and (Test-Path $path)) {
                Write-Output $path
                exit 0
            }
        }
        exit 1
        """
        
        result = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-Command', ps_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            ),
            timeout=3.0
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0 and stdout:
            path = stdout.decode('utf-8').strip()
            # Handle file:/// URLs
            if path.startswith('file:///'):
                path = path[8:].replace('/', '\\')
            if path and os.path.exists(path):
                logger.info(f"[EXPLORER_PATH] ✅ Fallback found: {path}")
                return path
        
        return None
        
    except Exception as e:
        logger.warning(f"[EXPLORER_PATH] Fallback failed: {e}")
        return None


async def _refresh_explorer():
    """Refresh File Explorer to show newly created items"""
    try:
        logger.info("[REFRESH] Refreshing File Explorer...")
        ps_script = """
        $shell = New-Object -ComObject Shell.Application
        $windows = $shell.Windows()
        foreach ($window in $windows) {
            try {
                if ($window.FullName -like "*explorer.exe*") {
                    $window.Refresh()
                }
            } catch {}
        }
        """
        
        # Run refresh asynchronously without waiting
        asyncio.create_task(
            asyncio.create_subprocess_exec(
                'powershell', '-NoProfile', '-Command', ps_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        )
        logger.info("[REFRESH] Refresh command sent")
    except Exception as e:
        # Don't fail if refresh doesn't work
        logger.warning(f"[REFRESH] Failed (non-critical): {e}")


def _translate_simple(text: str) -> str:
    """
    Simple translation for common Hindi words to English.
    No external API calls - fast and reliable.
    """
    # Common Hindi to English mappings
    translations = {
        # Folders/Files
        "फोल्डर": "folder",
        "फ़ोल्डर": "folder",
        "फाइल": "file",
        "फ़ाइल": "file",
        "दस्तावेज़": "documents",
        "दस्तावेज": "documents",
        "चित्र": "pictures",
        "तस्वीर": "pictures",
        "वीडियो": "videos",
        "संगीत": "music",
        "डाउनलोड": "downloads",
        
        # Common words
        "नया": "new",
        "पुराना": "old",
        "मेरा": "my",
        "प्रोजेक्ट": "project",
        "काम": "work",
        "घर": "home",
        "ऑफिस": "office",
        "स्कूल": "school",
        "कॉलेज": "college",
    }
    
    # Check if text contains Hindi characters
    has_hindi = any(ord(char) > 128 for char in text)
    
    if not has_hindi:
        return text  # Already in English
    
    # Try word-by-word translation
    words = text.split()
    translated_words = []
    
    for word in words:
        clean_word = word.strip()
        if clean_word in translations:
            translated_words.append(translations[clean_word])
        else:
            # Keep original if no translation found
            translated_words.append(word)
    
    result = ' '.join(translated_words)
    return result if result else text
