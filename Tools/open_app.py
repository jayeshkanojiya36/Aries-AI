from livekit.agents import function_tool
import subprocess
import webbrowser
import os
import asyncio
import json
import logging
from Tools.window_manager import WindowManager
from Tools.layout_engine import LayoutEngine
from Tools.validator import Validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App name → executable / URI mapping for common apps
# ---------------------------------------------------------------------------
APP_ALIASES = {
    # Browsers
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "microsoft edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "brave": "brave",
    "opera": "opera",

    # Microsoft Office
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "onenote": "onenote",
    "access": "msaccess",

    # Windows built-ins
    "notepad": "notepad",
    "calc": "calc",
    "calculator": "calc",
    "paint": "mspaint",
    "task manager": "taskmgr",
    "file explorer": "explorer",
    "explorer": "explorer",
    "control panel": "control",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "regedit": "regedit",
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "device manager": "devmgmt.msc",
    "disk management": "diskmgmt.msc",
    "services": "services.msc",
    "event viewer": "eventvwr.msc",
    "snipping tool": "snippingtool",
    "wordpad": "wordpad",
    "magnifier": "magnify",
    "narrator": "narrator",
    "on-screen keyboard": "osk",

    # Common apps
    "vlc": "vlc",
    "spotify": "spotify",
    "discord": "discord",
    "slack": "slack",
    "zoom": "zoom",
    "teams": "teams",
    "microsoft teams": "teams",
    "whatsapp": "whatsapp",
    "telegram": "telegram",
    "skype": "skype",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "visual studio": "devenv",
    "android studio": "studio",
    "pycharm": "pycharm",
    "steam": "steam",
    "obs": "obs64",
    "obs studio": "obs64",
    "gimp": "gimp-2.10",
    "notepad++": "notepad++",
    "7zip": "7zFM",
    "winrar": "winrar",
    "adobe reader": "acrobat",
    "acrobat": "acrobat",
    "photoshop": "photoshop",
    "blender": "blender",
    "audacity": "audacity",
}

# Sites where the name is enough to derive a URL
URL_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://www.twitter.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "github": "https://www.github.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
    "chatgpt": "https://chat.openai.com",
    "openai": "https://openai.com",
    "bing": "https://www.bing.com",
    "whatsapp web": "https://web.whatsapp.com",
}


def _is_url(text: str) -> bool:
    """Return True if text looks like a URL or web address."""
    text = text.strip().lower()
    return (
        text.startswith("http://")
        or text.startswith("https://")
        or text.startswith("www.")
        or (
            "." in text
            and not text.endswith(".exe")
            and not text.endswith(".msc")
            and " " not in text
        )
    )


def _open_url(url: str) -> str:
    """Open a URL in the default browser."""
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened URL: {url}"


def _run_app(cmd: str) -> str:
    """Launch an app using 'start' shell command (non-blocking)."""
    # ms- URIs and .msc snap-ins need special handling
    if cmd.startswith("ms-"):
        subprocess.Popen(f'start "" "{cmd}"', shell=True)
        return f"Opened system URI: {cmd}"
    if cmd.endswith(".msc"):
        subprocess.Popen(["mmc", cmd], shell=False)
        return f"Opened MMC snap-in: {cmd}"
    # Regular executable (uses Windows PATH + shell's start command)
    subprocess.Popen(f'start "" "{cmd}"', shell=True)
    return f"Launched: {cmd}"


@function_tool()
async def open_app(app_name: str) -> str:
    """
    Launches applications, system tools, or websites on the computer.

    IMPORTANT INSTRUCTIONS FOR ARGUMENT GENERATION:
    Pass the natural name or executable name. The tool handles mapping.

    Examples:
    - "Open Notepad"      -> app_name="notepad"
    - "Open Calculator"   -> app_name="calculator"
    - "Open VS Code"      -> app_name="vs code"
    - "Open Chrome"       -> app_name="chrome"
    - "Open YouTube"      -> app_name="youtube"
    - "Open Google"       -> app_name="google"
    - "Open Settings"     -> app_name="settings"
    - "Open WhatsApp"     -> app_name="whatsapp"

    Args:
        app_name: The app name, executable, URL, or website name.
    """
    try:
        key = app_name.strip().lower()

        # 1. Check website shortcuts first (e.g. "youtube", "google")
        if key in URL_SITES:
            result = await asyncio.to_thread(_open_url, URL_SITES[key])
            return f"Opened {app_name} in your browser."

        # 2. If it looks like a URL, open it directly
        if _is_url(key):
            result = await asyncio.to_thread(_open_url, app_name.strip())
            return f"Opened {app_name} in your browser."

        # 3. Check alias table
        if key in APP_ALIASES:
            cmd = APP_ALIASES[key]
            # Some aliases are full paths or URIs
            if cmd.startswith("ms-") or cmd.endswith(".msc"):
                result = await asyncio.to_thread(_run_app, cmd)
            elif os.path.isabs(cmd):
                # Full path — launch directly
                subprocess.Popen([cmd])
                result = f"Launched {app_name}"
            else:
                result = await asyncio.to_thread(_run_app, cmd)
            return f"Successfully opened {app_name}."

        # 4. Fallback: try launching the raw string as a command via 'start'
        result = await asyncio.to_thread(_run_app, app_name.strip())
        return f"Attempted to launch '{app_name}'. If it didn't open, make sure the app is installed and in PATH."

    except Exception as e:
        return f"Failed to open '{app_name}': {str(e)}"

class AppController:
    @staticmethod
    async def open_app(name: str) -> dict:
        logger.info(f"Opening app: {name}")
        win = WindowManager.get_window_by_app_name(name)
        if win:
            WindowManager.focus(win)
            return {"status": "success", "message": f"{name} was already running and is now focused."}
            
        key = name.strip().lower()
        
        if key in URL_SITES:
            webbrowser.open(URL_SITES[key])
            return {"status": "success", "message": f"Opened {name} in browser."}
            
        if _is_url(key):
            url = key if key.startswith("http") else "https://" + key
            webbrowser.open(url)
            return {"status": "success", "message": f"Opened {name} in browser."}
            
        cmd = APP_ALIASES.get(key, name)
        
        try:
            subprocess.Popen(f'start "" "{cmd}"', shell=True)
            return {"status": "success", "message": f"Opened {name}"}
        except Exception as e:
            logger.error(f"Failed to open '{name}': {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def close_app(name: str) -> dict:
        win = WindowManager.get_window_by_app_name(name)
        if win:
            if WindowManager.close(win):
                return {"status": "success", "message": f"Closed {name}."}
            return {"status": "error", "message": f"Failed to close {name}."}
        return {"status": "error", "message": f"{name} is not currently running."}

    @staticmethod
    async def focus_app(name: str) -> dict:
        win = WindowManager.get_window_by_app_name(name)
        if win:
            if WindowManager.focus(win):
                return {"status": "success", "message": f"Focused {name}."}
            return {"status": "error", "message": f"Failed to focus {name}."}
        return {"status": "error", "message": f"{name} is not currently running."}

    @staticmethod
    async def minimize_app(name: str) -> dict:
        win = WindowManager.get_window_by_app_name(name)
        if win:
            if WindowManager.minimize(win):
                return {"status": "success", "message": f"Minimized {name}."}
            return {"status": "error", "message": f"Failed to minimize {name}."}
        return {"status": "error", "message": f"{name} is not currently running."}

    @staticmethod
    async def maximize_app(name: str) -> dict:
        win = WindowManager.get_window_by_app_name(name)
        if win:
            if WindowManager.maximize(win):
                return {"status": "success", "message": f"Maximized {name}."}
            return {"status": "error", "message": f"Failed to maximize {name}."}
        return {"status": "error", "message": f"{name} is not currently running."}

    @staticmethod
    async def arrange_apps(layout: str, apps: list) -> dict:
        return LayoutEngine.arrange(layout, apps)

@function_tool()
async def smart_app_controller(intent_json: str) -> str:
    """
    Receives a structured JSON intent from the LLM to control desktop apps.
    Supported actions: open_app, close_app, focus_app, minimize_app, maximize_app, arrange_apps.
    
    Example input:
    {"action": "arrange_apps", "layout": "split", "apps": [{"name": "chrome", "position": "left"}]}
    """
    logger.info(f"Received smart_app_controller intent: {intent_json}")
    try:
        intent = json.loads(intent_json)
    except json.JSONDecodeError:
        return json.dumps({"status": "error", "message": "Invalid JSON format."})
        
    validation = Validator.validate_intent(intent)
    if not validation["valid"]:
        return json.dumps({"status": "error", "message": validation["message"]})
        
    action = intent.get("action")
    
    try:
        if action == "open_app":
            result = await AppController.open_app(intent.get("name", ""))
        elif action == "close_app":
            result = await AppController.close_app(intent.get("name", ""))
        elif action == "focus_app":
            result = await AppController.focus_app(intent.get("name", ""))
        elif action == "minimize_app":
            result = await AppController.minimize_app(intent.get("name", ""))
        elif action == "maximize_app":
            result = await AppController.maximize_app(intent.get("name", ""))
        elif action == "arrange_apps":
            result = await AppController.arrange_apps(intent.get("layout", ""), intent.get("apps", []))
        else:
            result = {"status": "error", "message": "Unhandled action."}
    except Exception as e:
        logger.error(f"Error handling action '{action}': {e}")
        result = {"status": "error", "message": f"Internal execution error: {str(e)}"}
        
    return json.dumps(result)
