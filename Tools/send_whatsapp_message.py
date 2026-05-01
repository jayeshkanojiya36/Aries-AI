import pyautogui
import asyncio
import aiohttp
import json
from livekit.agents import function_tool

# --- Global State for Call Tracking ---
LAST_DETECTED_CONTACT = "Unknown"

async def translate_to_english_free(text: str) -> str:
    """
    Translate text to English using free APIs without API keys
    """
    if not text.strip():
        return text
    
    # Check if text is already in English
    if is_english(text):
        return text
    
    # Try multiple free translation services
    translation = await try_google_translate(text)
    if translation:
        return translation
    
    translation = await try_my_memory_translate(text)
    if translation:
        return translation
    
    translation = await try_libretranslate(text)
    if translation:
        return translation
    
    # Fallback to basic translation if all APIs fail
    return fallback_translation(text)

def is_english(text: str) -> bool:
    """Check if text is already in English"""
    try:
        return all(ord(char) < 128 or char.isspace() for char in text)
    except:
        return True

async def try_google_translate(text: str) -> str:
    """
    Try Google Translate (free unofficial API)
    """
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': 'auto',  # source language (auto-detect)
            'tl': 'en',    # target language (English)
            'dt': 't',
            'q': text
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Extract translated text from response
                    if data and len(data) > 0:
                        translated_parts = [part[0] for part in data[0] if part[0]]
                        return ''.join(translated_parts)
    except Exception as e:
        print(f"Google Translate failed: {e}")
    return None

async def try_my_memory_translate(text: str) -> str:
    """
    Try MyMemory Translation API (free)
    """
    try:
        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text,
            'langpair': 'auto|en'
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('responseStatus') == 200:
                        return data['responseData']['translatedText']
    except Exception as e:
        print(f"MyMemory Translate failed: {e}")
    return None

async def try_libretranslate(text: str) -> str:
    """
    Try LibreTranslate (free open-source)
    """
    try:
        # Try different LibreTranslate instances
        instances = [
            "https://libretranslate.de/translate",
            "https://translate.argosopentech.com/translate",
            "https://libretranslate.pussthecat.org/translate"
        ]
        
        payload = {
            'q': text,
            'source': 'auto',
            'target': 'en',
            'format': 'text'
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            for instance_url in instances:
                try:
                    async with session.post(instance_url, 
                                          data=json.dumps(payload), 
                                          headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data.get('translatedText')
                except:
                    continue  # Try next instance
                    
    except Exception as e:
        print(f"LibreTranslate failed: {e}")
    return None

def fallback_translation(text: str) -> str:
    """
    Basic fallback translation for common words
    """
    basic_translations = {
        # Hindi
        "नमस्ते": "hello", "हैलो": "hello", "हाय": "hi", "कैसे": "how", "हो": "are",
        "आप": "you", "तुम": "you", "मैं": "I", "मेरा": "my", "नाम": "name",
        "धन्यवाद": "thank you", "शुक्रिया": "thanks", "कृपया": "please",
        "हाँ": "yes", "ना": "no", "नहीं": "no", "ठीक": "ok", "अच्छा": "good",
        
        # Actions
        "लिखो": "write", "टाइप": "type", "बनाओ": "make", "करो": "do",
        "दिखाओ": "show", "भेजो": "send", "खोलो": "open", "बंद": "close",
        
        # Common words
        "मदद": "help", "समय": "time", "दिन": "day", "रात": "night",
        "क्या": "what", "क्यों": "why", "कब": "when", "कहाँ": "where"
    }
    
    words = text.split()
    translated_words = []
    
    for word in words:
        clean_word = word.strip('.,!?;:').lower()
        if clean_word in basic_translations:
            translated_words.append(basic_translations[clean_word])
        else:
            translated_words.append(word)
    
    return ' '.join(translated_words)




import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum
from livekit.agents import function_tool
import pyautogui
import time


class WhatsAppState(Enum):
    """State machine for WhatsApp automation"""
    INITIAL = "initial"
    SEARCHING = "searching"
    CONTACT_FOUND = "contact_found"
    MESSAGE_SENT = "message_sent"
    ERROR = "error"


@dataclass
class AutomationConfig:
    """Configuration for automation parameters"""
    key_press_delay: float = 0.08  # Increased for stability
    search_timeout: float = 10.0   # Increased timeout
    animation_wait: float = 2.0    # Increased for slow systems
    fail_safe: bool = True
    pause_duration: float = 0.1    # Increased pause
    mode: str = "balanced"  # balanced, fast, reliable


class WhatsAppAutomationError(Exception):
    """Custom exception for WhatsApp automation failures"""
    pass


class AdvancedWhatsAppSender:
    """
    Advanced WhatsApp message sender with optimized performance
    Uses state machine pattern for reliable automation
    """
    
    def __init__(self, config: Optional[AutomationConfig] = None):
        self.config = config or AutomationConfig()
        self.logger = self._setup_logger()
        self.state = WhatsAppState.INITIAL
        
        # Initialize pyautogui settings
        pyautogui.FAILSAFE = self.config.fail_safe
        pyautogui.PAUSE = self.config.pause_duration
        
    def _setup_logger(self) -> logging.Logger:
        """Setup advanced logging"""
        logger = logging.getLogger("AdvancedWhatsAppSender")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    async def _execute_with_retry(self, 
                                action: Callable, 
                                max_retries: int = 3,
                                delay: float = 1.5) -> bool:  # Increased delay
        """
        Execute action with retry mechanism
        """
        for attempt in range(max_retries):
            try:
                await asyncio.to_thread(action)
                return True
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                continue
        return False
    
    async def _smart_wait(self, duration: float = None):
        """Intelligent waiting with dynamic duration"""
        wait_time = duration or self.config.animation_wait
        self.logger.info(f"⏳ Waiting for {wait_time}s...")
        await asyncio.sleep(wait_time)
    
    async def _open_whatsapp(self) -> bool:
        """Open WhatsApp using Windows search with optimized approach"""
        try:
            self.logger.info("🔍 Opening WhatsApp...")
            
            # Press Windows key
            if not await self._execute_with_retry(lambda: pyautogui.press('win')):
                raise WhatsAppAutomationError("Failed to press Windows key")
            
            await self._smart_wait(1.0)  # Increased wait
            
            # Type WhatsApp - using English for universal compatibility
            if not await self._execute_with_retry(
                lambda: pyautogui.typewrite('whatsapp', interval=self.config.key_press_delay)
            ):
                raise WhatsAppAutomationError("Failed to type WhatsApp")
            
            await self._smart_wait(0.8)  # Increased wait
            
            # Press Enter
            if not await self._execute_with_retry(lambda: pyautogui.press('enter')):
                raise WhatsAppAutomationError("Failed to open WhatsApp")
            
            # Wait for WhatsApp to load - increased time
            await self._smart_wait(4.0)  # Increased for slow loading
            
            self.state = WhatsAppState.SEARCHING
            self.logger.info("✅ WhatsApp opened successfully")
            return True
            
        except Exception as e:
            self.state = WhatsAppState.ERROR
            self.logger.error(f"❌ Failed to open WhatsApp: {e}")
            raise WhatsAppAutomationError(f"WhatsApp opening failed: {str(e)}")
    
    async def _search_and_select_contact(self, contact: str) -> bool:
        """Advanced contact search with timeout handling"""
        try:
            self.logger.info(f"👤 Searching for contact: {contact}")
            start_time = time.time()
            
            # Press Ctrl+F for search - universal shortcut
            if not await self._execute_with_retry(
                lambda: pyautogui.hotkey('ctrl', 'f')
            ):
                raise WhatsAppAutomationError("Search shortcut failed")
            
            await self._smart_wait(2.0)  # Increased wait for search to open
            
            # Clear any existing text and type contact name
            if not await self._execute_with_retry(
                lambda: pyautogui.hotkey('ctrl', 'a')  # Select all
            ):
                self.logger.warning("⚠️ Select all failed, continuing...")
            
            # Type contact name with reasonable speed
            contact = await translate_to_english_free(contact)
            
            if not await self._execute_with_retry(
                lambda: pyautogui.typewrite(contact, interval=0.1)  # Slower typing for reliability
            ):
                raise WhatsAppAutomationError("Contact typing failed")
            
            await self._smart_wait(2.0)  # Increased wait for search results
            
            # Select and open contact
            if not await self._execute_with_retry(lambda: pyautogui.press('down')):
                self.logger.warning("⚠️ Down arrow failed, trying direct enter...")
                # Try direct enter if down fails
                if not await self._execute_with_retry(lambda: pyautogui.press('enter')):
                    raise WhatsAppAutomationError("Contact selection failed")
            else:
                await self._smart_wait(0.5)
                if not await self._execute_with_retry(lambda: pyautogui.press('enter')):
                    raise WhatsAppAutomationError("Contact opening failed")
            
            await self._smart_wait(2.0)  # Increased wait for chat to open
            
            # Check timeout
            elapsed_time = time.time() - start_time
            if elapsed_time > self.config.search_timeout:
                self.logger.warning(f"⚠️ Search took {elapsed_time:.1f}s (timeout: {self.config.search_timeout}s)")
                # Don't raise error immediately, continue if possible
            
            self.state = WhatsAppState.CONTACT_FOUND
            self.logger.info(f"✅ Contact '{contact}' selected successfully")
            return True
            
        except Exception as e:
            self.state = WhatsAppState.ERROR
            self.logger.error(f"❌ Contact search failed: {e}")
            raise WhatsAppAutomationError(f"Contact search failed: {str(e)}")
    
    async def _send_message(self, message: str) -> bool:
        """Optimized message sending with validation"""
        try:
            self.logger.info(f"📝 Typing message: {message[:50]}...")
            
            # Type message with reasonable speed
            message = await translate_to_english_free(message)
            if not await self._execute_with_retry(
                lambda: pyautogui.typewrite(message, interval=0.07)  # Balanced typing speed
            ):
                raise WhatsAppAutomationError("Message typing failed")
            
            await self._smart_wait(0.5)  # Wait before sending
            
            # Send message
            if not await self._execute_with_retry(lambda: pyautogui.press('enter')):
                raise WhatsAppAutomationError("Message sending failed")
            
            await self._smart_wait(1.0)  # Wait after sending
            
            self.state = WhatsAppState.MESSAGE_SENT
            self.logger.info("✅ Message sent successfully")
            return True
            
        except Exception as e:
            self.state = WhatsAppState.ERROR
            self.logger.error(f"❌ Message sending failed: {e}")
            raise WhatsAppAutomationError(f"Message sending failed: {str(e)}")


# Single function tool with multiple modes
@function_tool()
async def send_whatsapp_message(contact: str, message: str, mode: str = "balanced") -> str:
    """
    Advanced WhatsApp message sender with multiple optimization modes.
    Uses English search for universal compatibility.
    
    Args:
        contact: Contact name/number (English search compatible)
        message: Message content to send
        mode: Operation mode - "fast", "balanced", "reliable"
        
    Returns:
        str: Delivery confirmation with follow-up prompt
    """
    
    # Configuration based on mode - increased delays for stability
    configs = {
        "fast": AutomationConfig(
            key_press_delay=0.06,    # Balanced speed
            search_timeout=12.0,     # Increased timeout
            animation_wait=1.5,      # Reasonable waits
            pause_duration=0.08,
            mode="fast"
        ),
        "balanced": AutomationConfig(
            key_press_delay=0.08,    # Reliable speed
            search_timeout=15.0,     # Good timeout
            animation_wait=2.0,
            pause_duration=0.1,
            mode="balanced"
        ),
        "reliable": AutomationConfig(
            key_press_delay=0.1,     # Slow and steady
            search_timeout=20.0,     # Maximum timeout
            animation_wait=3.0,      # Maximum waits
            pause_duration=0.15,
            mode="reliable"
        )
    }
    
    config = configs.get(mode, configs["balanced"])
    sender = AdvancedWhatsAppSender(config)
    
    try:
        sender.logger.info(f"🚀 Starting WhatsApp send: {contact} | Mode: {mode}")
        
        # Store original mouse position
        original_pos = await asyncio.to_thread(pyautogui.position)
        sender.logger.info(f"📍 Original position: {original_pos}")
        
        # Execute automation pipeline
        await sender._open_whatsapp()
        await sender._search_and_select_contact(contact)
        await sender._send_message(message)
        
        # Return to original position
        await asyncio.to_thread(
            pyautogui.moveTo, original_pos.x, original_pos.y, duration=0.1
        )
        
        # Response based on mode
        responses = {
            "fast": f"⚡ Rapid delivery to '{contact}': \"{message}\"\n💡 Send another message?",
            "balanced": f"✅ Message sent successfully to '{contact}': \"{message}\"\n🧠 Would you like to send another message?",
            "reliable": f"🛡️ Reliably delivered to '{contact}': \"{message}\"\n🤖 Ready for next message command."
        }
        
        success_response = responses.get(mode, responses["balanced"])
        sender.logger.info(f"🎉 WhatsApp message sent successfully in {mode} mode")
        return success_response
        
    except WhatsAppAutomationError as e:
        error_msg = f"❌ WhatsApp automation failed: {str(e)}"
        sender.logger.error(error_msg)
        return error_msg
        
    except Exception as e:
        error_msg = f"❌ Unexpected error in WhatsApp sending: {str(e)}"
        sender.logger.error(error_msg)
        return error_msg


    return await send_whatsapp_message(contact, message, "balanced")


@function_tool()
async def reply_to_caller(message: str) -> str:
    """
    Sends a WhatsApp message to the contact who most recently called.
    
    Args:
        message: Content to send
    """
    global LAST_DETECTED_CONTACT
    if LAST_DETECTED_CONTACT == "Unknown":
        return "❌ Error: No incoming call contact detected recently."
        
    return await send_whatsapp_message(LAST_DETECTED_CONTACT, message, "balanced")

# --- WhatsApp Call Automation Components ---
import pygetwindow as gw
import win32gui
import win32con
import psutil
import os
from pywinauto.application import Application
from typing import Dict

# Provide a logger
whats_auto_logger = logging.getLogger("WhatsAppAuto")
if not whats_auto_logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    whats_auto_logger.addHandler(ch)
    whats_auto_logger.setLevel(logging.INFO)

class ContactFilter:
    def __init__(self):
        self.AUTHORIZED_CONTACTS = ["Rahul", "Aman"]
        whats_auto_logger.info("ContactFilter initialized with authorized contacts: %s", self.AUTHORIZED_CONTACTS)

    def is_authorized(self, contact_name: str) -> bool:
        if not contact_name:
            return False
        
        for authorized in self.AUTHORIZED_CONTACTS:
            if authorized.lower() in contact_name.lower():
                whats_auto_logger.info("Contact '%s' is authorized.", contact_name)
                return True
                
        whats_auto_logger.info("Contact '%s' is NOT authorized.", contact_name)
        return False

class WindowController:
    def __init__(self):
        self.process_name = "WhatsApp.exe"
        self.window_title_keywords = ["WhatsApp Call", "Incoming voice call", "Video call", "Voice call", "WhatsApp"]

    def is_whatsapp_running(self) -> bool:
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and self.process_name.lower() in proc.info['name'].lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def launch_whatsapp(self) -> bool:
        whats_auto_logger.info("WhatsApp is not running. Launching via OS protocol...")
        try:
            os.startfile("whatsapp:")
            time.sleep(5)
            return True
        except Exception as e:
            whats_auto_logger.error("Failed to launch WhatsApp: %s", str(e))
            return False

    def get_whatsapp_windows(self):
        windows = []
        try:
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    for keyword in self.window_title_keywords:
                        if keyword.lower() in title.lower():
                            windows.append((hwnd, title))
                            break
            win32gui.EnumWindows(callback, None)
        except Exception as e:
            whats_auto_logger.error("Error enumerating windows: %s", str(e))
        return windows
        
    def find_call_window(self):
        windows = self.get_whatsapp_windows()
        for hwnd, title in windows:
            if "call" in title.lower() or "incoming" in title.lower():
                return hwnd, title
        return None, None
        
    def bring_to_foreground(self, hwnd) -> bool:
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            whats_auto_logger.info("Brought window (HWND: %s) to foreground.", hwnd)
            return True
        except Exception as e:
            whats_auto_logger.error("Failed to bring window to foreground: %s", str(e))
            return False
            
    def get_window_text_content(self, hwnd) -> str:
        try:
            title = win32gui.GetWindowText(hwnd)
            return title
        except Exception:
            return ""

class ClickEngine:
    def __init__(self):
        self.calibration: Dict[str, tuple] = {
            "accept_button": None,
            "reject_button": None
        }
        
    def set_calibration(self, button: str, x: int, y: int):
        if button in self.calibration:
            self.calibration[button] = (x, y)
            whats_auto_logger.info("Calibrated %s to coordinates (%d, %d)", button, x, y)
            
    def click_accept(self, window_handle) -> bool:
        whats_auto_logger.info("Attempting to click ACCEPT button.")
        
        try:
            app = Application(backend="uia").connect(handle=window_handle, timeout=2)
            dlg = app.window(handle=window_handle)
            accept_btn = None
            try:
                accept_btn = dlg.child_window(title="Accept", control_type="Button")
                if not accept_btn.exists():
                    accept_btn = dlg.child_window(title="Answer", control_type="Button")
            except Exception:
                pass

            if accept_btn and accept_btn.exists():
                accept_btn.click_input()
                whats_auto_logger.info("Clicked ACCEPT via pywinauto control identifier.")
                return True
        except Exception as e:
            whats_auto_logger.warning("pywinauto accept click failed: %s", str(e))

        try:
            location = pyautogui.locateCenterOnScreen('accept_button.png', confidence=0.8)
            if location:
                pyautogui.click(location)
                whats_auto_logger.info("Clicked ACCEPT via image recognition.")
                return True
        except Exception as e:
            whats_auto_logger.warning("Image recognition for accept failed or image not found: %s", str(e))
            
        if self.calibration["accept_button"]:
            try:
                x, y = self.calibration["accept_button"]
                pyautogui.click(x, y)
                whats_auto_logger.info("Clicked ACCEPT via calibrated coordinates.")
                return True
            except Exception as e:
                whats_auto_logger.warning("Coordinate click failed: %s", str(e))
                
        whats_auto_logger.error("Failed to click ACCEPT using all fallback strategies.")
        return False

    def click_reject(self, window_handle) -> bool:
        whats_auto_logger.info("Attempting to click REJECT button.")
        
        try:
            app = Application(backend="uia").connect(handle=window_handle, timeout=2)
            dlg = app.window(handle=window_handle)
            reject_btn = None
            try:
                reject_btn = dlg.child_window(title="Decline", control_type="Button")
                if not reject_btn.exists():
                    reject_btn = dlg.child_window(title="Reject", control_type="Button")
            except Exception:
                pass

            if reject_btn and reject_btn.exists():
                reject_btn.click_input()
                whats_auto_logger.info("Clicked REJECT via pywinauto control identifier.")
                return True
        except Exception as e:
            whats_auto_logger.warning("pywinauto reject click failed: %s", str(e))

        try:
            location = pyautogui.locateCenterOnScreen('reject_button.png', confidence=0.8)
            if location:
                pyautogui.click(location)
                whats_auto_logger.info("Clicked REJECT via image recognition.")
                return True
        except Exception as e:
            whats_auto_logger.warning("Image recognition for reject failed or image not found: %s", str(e))
            
        if self.calibration["reject_button"]:
            try:
                x, y = self.calibration["reject_button"]
                pyautogui.click(x, y)
                whats_auto_logger.info("Clicked REJECT via calibrated coordinates.")
                return True
            except Exception as e:
                whats_auto_logger.warning("Coordinate click failed: %s", str(e))
                
        whats_auto_logger.error("Failed to click REJECT using all fallback strategies.")
        return False