import time
import threading
import json
import pyautogui
from .send_whatsapp_message import WindowController, ClickEngine, ContactFilter, whats_auto_logger as logger

class CallMonitor:
    def __init__(self):
        self.window_ctrl = WindowController()
        self.click_engine = ClickEngine()
        self.contact_filter = ContactFilter()
        
        self.is_running = False
        self.monitor_thread = None
        
        self.active_call_processed = False

    def start_monitoring(self):
        if self.is_running:
            return
        
        # We no longer launch WhatsApp automatically to prevent it randomly opening on boot
        # if not self.window_ctrl.is_whatsapp_running():
        #     self.window_ctrl.launch_whatsapp()

        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Call monitoring thread started.")

    def stop_monitoring(self):
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Call monitoring stopped.")

    def _extract_contact_name_from_title(self, title: str) -> str:
        for contact in self.contact_filter.AUTHORIZED_CONTACTS:
            if contact.lower() in title.lower():
                return contact
                
        return "Unknown"

    def _monitor_loop(self):
        while self.is_running:
            try:
                hwnd, title = self.window_ctrl.find_call_window()
                
                if hwnd and not self.active_call_processed:
                    logger.info("Incoming call detected. Window Title: '%s'", title)
                    self.active_call_processed = True
                    
                    self.window_ctrl.bring_to_foreground(hwnd)
                    contact_name = self._extract_contact_name_from_title(title)
                    
                    # Update global tracking
                    import Tools.send_whatsapp_message as wm
                    wm.LAST_DETECTED_CONTACT = contact_name
                    
                    if self.contact_filter.is_authorized(contact_name):
                        self._handle_accept(hwnd, contact_name)
                    else:
                        self._handle_reject(hwnd, contact_name)
                        
                elif not hwnd:
                    self.active_call_processed = False
                
                time.sleep(1)
                
            except Exception as e:
                logger.error("Error in CallMonitor loop: %s", str(e))
                time.sleep(2) 

    def _handle_accept(self, hwnd, contact_name):
        logger.info("Handling ACCEPT for authorized contact: %s", contact_name)
        success = self.click_engine.click_accept(hwnd)
        if success:
            logger.info("Call accepted. Sending auto-response message.")
            result = {"status": "call_accepted", "contact": contact_name}
            print(json.dumps(result))
            
            self._send_auto_response(contact_name)
        else:
            logger.error("Failed to accept call.")
            result = {"status": "error", "message": "Failed to accept call", "contact": contact_name}
            print(json.dumps(result))

    def _handle_reject(self, hwnd, contact_name):
        logger.info("Handling REJECT for unauthorized contact: %s", contact_name)
        success = self.click_engine.click_reject(hwnd)
        if success:
            logger.info("Call rejected safely.")
            result = {"status": "call_rejected", "contact": contact_name}
            print(json.dumps(result))
        else:
            logger.error("Failed to reject call.")
            result = {"status": "error", "message": "Failed to reject call", "contact": contact_name}
            print(json.dumps(result))

    def _send_auto_response(self, contact_name):
        try:
            time.sleep(2)
            msg = f"Jarvis auto-answered this call. The user is currently unavailable."
            logger.info("Sending auto-response to '%s' via full automation...", contact_name)
            
            # Use the robust AdvancedWhatsAppSender to properly deliver the message
            import asyncio
            from .send_whatsapp_message import AdvancedWhatsAppSender, AutomationConfig
            
            async def _send_async():
                config = AutomationConfig(mode="balanced")
                sender = AdvancedWhatsAppSender(config)
                # Full automation: open whatsapp, search contact, send message
                await sender._open_whatsapp()
                await sender._search_and_select_contact(contact_name)
                await sender._send_message(msg)
                
            asyncio.run(_send_async())
            logger.info("Auto-response message successfully delivered to: '%s'", contact_name)
        except Exception as e:
            logger.error("Failed to send auto-response: %s", str(e))
