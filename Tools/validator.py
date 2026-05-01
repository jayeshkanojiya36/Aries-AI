import logging

logger = logging.getLogger(__name__)

class Validator:
    ALLOWED_ACTIONS = {
        "open_app", "close_app", "focus_app", 
        "minimize_app", "maximize_app", "arrange_apps"
    }

    @staticmethod
    def validate_intent(intent: dict) -> dict:
        action = intent.get("action")
        logger.info(f"Validating intent action: {action}")
        
        if action == "blocked":
            return {"valid": False, "message": "Action blocked by safety rules."}
            
        if action == "unknown":
            return {"valid": False, "message": "Command unclear or unknown."}
            
        if action not in Validator.ALLOWED_ACTIONS:
            return {"valid": False, "message": f"Action '{action}' is not allowed."}
            
        if action in ("open_app", "close_app", "focus_app", "minimize_app", "maximize_app"):
            name = intent.get("name", "")
            if Validator._has_shell_injection(name):
                logger.warning(f"Shell injection detected in name: {name}")
                return {"valid": False, "message": "Potential shell injection detected."}
                
        if action == "arrange_apps":
            apps = intent.get("apps", [])
            for app in apps:
                name = app.get("name", "")
                if Validator._has_shell_injection(name):
                    logger.warning(f"Shell injection detected in nested app name: {name}")
                    return {"valid": False, "message": "Potential shell injection detected in apps payload."}

        return {"valid": True, "message": "Valid intent."}

    @staticmethod
    def _has_shell_injection(text: str) -> bool:
        if not isinstance(text, str):
            return False
        forbidden = [";", "&", "|", ">", "<", "`", "$", "(", ")", "\n", "\r"]
        return any(f in text for f in forbidden)
