import logging
from Tools.window_manager import WindowManager

logger = logging.getLogger(__name__)

class LayoutEngine:
    @staticmethod
    def arrange(layout: str, apps: list) -> dict:
        logger.info(f"Arranging layout: {layout} for apps: {apps}")
        screen_w, screen_h = WindowManager.get_screen_resolution()
        
        if layout == "split":
            if len(apps) == 2:
                left_app = next((a["name"] for a in apps if a.get("position") == "left"), apps[0]["name"])
                right_app = next((a["name"] for a in apps if a.get("position") == "right"), apps[1]["name"])
                
                win_l = WindowManager.get_window_by_app_name(left_app)
                win_r = WindowManager.get_window_by_app_name(right_app)
                
                if win_l:
                    WindowManager.move_and_resize(win_l, 0, 0, screen_w // 2, screen_h)
                if win_r:
                    WindowManager.move_and_resize(win_r, screen_w // 2, 0, screen_w // 2, screen_h)
                    
                return {"status": "success", "message": "Apps arranged in split layout."}
            elif len(apps) == 1:
                pos = apps[0].get("position", "left")
                win = WindowManager.get_window_by_app_name(apps[0]["name"])
                
                # Automatically snap Jarvis (Electron) to the opposite side
                jarvis_win = WindowManager.get_window_by_app_name("Jarvis AI")
                
                if win:
                    if pos == "right":
                        WindowManager.move_and_resize(win, screen_w // 2, 0, screen_w // 2, screen_h)
                        if jarvis_win:
                            WindowManager.move_and_resize(jarvis_win, 0, 0, screen_w // 2, screen_h)
                    else:
                        WindowManager.move_and_resize(win, 0, 0, screen_w // 2, screen_h)
                        if jarvis_win:
                            WindowManager.move_and_resize(jarvis_win, screen_w // 2, 0, screen_w // 2, screen_h)
                    return {"status": "success", "message": f"App split to {pos}, Jarvis moved to opposite."}
                return {"status": "error", "message": f"App {apps[0]['name']} not found."}
            
        elif layout == "fullscreen" and len(apps) >= 1:
            win = WindowManager.get_window_by_app_name(apps[0]["name"])
            if win:
                WindowManager.maximize(win)
                return {"status": "success", "message": "App set to fullscreen."}
            return {"status": "error", "message": f"App {apps[0]['name']} not found."}
            
        elif layout == "grid":
            positions = [
                (0, 0, screen_w // 2, screen_h // 2),
                (screen_w // 2, 0, screen_w // 2, screen_h // 2),
                (0, screen_h // 2, screen_w // 2, screen_h // 2),
                (screen_w // 2, screen_h // 2, screen_w // 2, screen_h // 2)
            ]
            count = min(len(apps), 4)
            for i in range(count):
                win = WindowManager.get_window_by_app_name(apps[i]["name"])
                if win:
                    x, y, w, h = positions[i]
                    WindowManager.move_and_resize(win, x, y, w, h)
            return {"status": "success", "message": "Apps arranged in grid layout."}
            
        elif layout in ["left", "right", "top", "bottom"] and len(apps) >= 1:
            win = WindowManager.get_window_by_app_name(apps[0]["name"])
            if not win:
                return {"status": "error", "message": f"App {apps[0]['name']} not found."}
                
            if layout == "left":
                WindowManager.move_and_resize(win, 0, 0, screen_w // 2, screen_h)
            elif layout == "right":
                WindowManager.move_and_resize(win, screen_w // 2, 0, screen_w // 2, screen_h)
            elif layout == "top":
                WindowManager.move_and_resize(win, 0, 0, screen_w, screen_h // 2)
            elif layout == "bottom":
                WindowManager.move_and_resize(win, 0, screen_h // 2, screen_w, screen_h // 2)
            return {"status": "success", "message": f"App snapped to {layout}."}
            
        return {"status": "error", "message": "Layout configuration not supported or invalid number of apps."}
