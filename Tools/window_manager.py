import logging
import pygetwindow as gw
import win32gui
import win32con
import win32process
import psutil

logger = logging.getLogger(__name__)

class WindowManager:
    @staticmethod
    def get_window_by_app_name(app_name: str):
        if not app_name:
            return None
            
        app_name_lower = app_name.lower()
        try:
            windows = gw.getAllWindows()
        except Exception as e:
            logger.error(f"Failed to get windows: {e}")
            return None
        
        # 1. Exact match first
        for win in windows:
            if app_name_lower == win.title.lower():
                logger.info(f"Found exact window match for {app_name}")
                return win
                
        # 2. Substring match
        for win in windows:
            if app_name_lower in win.title.lower() and win.title.strip() != "":
                logger.info(f"Found substring window match for {app_name}")
                return win
                
        # 3. Process name match via psutil
        logger.info(f"Attempting process name search for {app_name}")
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    p = psutil.Process(pid)
                    if app_name_lower in p.name().lower():
                        hwnds.append(hwnd)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        
        hwnds = []
        try:
            win32gui.EnumWindows(callback, hwnds)
        except Exception as e:
            logger.error(f"EnumWindows failed: {e}")
            
        if hwnds:
            title = win32gui.GetWindowText(hwnds[0])
            for win in windows:
                if win.title == title:
                    logger.info(f"Found process match window for {app_name}")
                    return win
            try:
                return gw.Win32Window(hwnds[0])
            except Exception as e:
                logger.error(f"Failed to wrap hwnd: {e}")
                
        return None

    @staticmethod
    def focus(win):
        if not win:
            return False
        try:
            if win.isMinimized:
                win.restore()
            win.activate()
            return True
        except Exception as e:
            logger.error(f"pygetwindow focus failed: {e}")
            try:
                if getattr(win, '_hWnd', None):
                    win32gui.ShowWindow(win._hWnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(win._hWnd)
                    return True
            except Exception as e2:
                logger.error(f"win32gui fallback focus failed: {e2}")
        return False

    @staticmethod
    def close(win):
        if win:
            try:
                win.close()
                return True
            except Exception as e:
                logger.error(f"Close failed: {e}")
        return False

    @staticmethod
    def minimize(win):
        if win:
            try:
                win.minimize()
                return True
            except Exception as e:
                logger.error(f"Minimize failed: {e}")
        return False

    @staticmethod
    def maximize(win):
        if win:
            try:
                win.maximize()
                return True
            except Exception as e:
                logger.error(f"Maximize failed: {e}")
        return False

    @staticmethod
    def move_and_resize(win, x: int, y: int, width: int, height: int):
        if win:
            try:
                if win.isMinimized or win.isMaximized:
                    win.restore()
                win.moveTo(x, y)
                win.resizeTo(width, height)
                return True
            except Exception as e:
                logger.error(f"Move/Resize failed: {e}")
        return False

    @staticmethod
    def get_screen_resolution():
        try:
            import win32api
            w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
            h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
            return w, h
        except Exception as e:
            logger.error(f"Failed to get resolution: {e}")
            return 1920, 1080
