import asyncio
import logging
import json
import os
import re
from typing import Optional, Dict, Literal
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("youtube_controller.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("YouTubeController")

class YouTubeController:
    """
    A modular YouTube controller using Playwright.
    Supports playback control, search, ad skipping, and state persistence.
    """
    
    def __init__(self, headless: bool = False, use_profile: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False
        self._ad_task = None
        
        # Paths
        self.base_dir = Path(__file__).parent
        self.storage_path = self.base_dir / "youtube_state.json"
        
        # Load state
        self.state = self._load_state()
        
        # Selectors
        self.selectors = {
            "search_input": "input#search",
            "video_title": "ytd-video-renderer #video-title",
            "play_pause_btn": ".ytp-play-button",
            "skip_ad_btn": ".ytp-ad-skip-button, .ytp-ad-skip-button-modern",
            "video_player": "#movie_player.html5-video-player",
            "ad_module": ".ytp-ad-module",
            "duration": ".ytp-time-duration",
            "current_time": ".ytp-time-current"
        }

    def _load_state(self) -> Dict:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
        return {"last_video": None, "timestamp": 0}

    def _save_state(self):
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    async def initialize(self):
        """Initialize the browser and page."""
        if self.is_running and self.page:
            try:
                # fast check if page is alive
                await asyncio.wait_for(self.page.title(), timeout=2)
                return
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Browser appears disconnected ({str(e)}), re-initializing...")
                await self.reset()

        logger.info("Initializing YouTube Controller...")
        try:
            # Ensure previous browser is fully shut down
            if self.browser is not None:
                try:
                    await self.browser.close()
                except:
                    pass
                self.browser = None

            self.playwright = await async_playwright().start()
            
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--window-size=1024,768"  # Set window size instead of maximizing
            ]
            
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=launch_args,
                channel="chrome"  # Try to use installed Chrome for codecs
            )
            
            self.context = await self.browser.new_context(
                viewport={"width": 1024, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            
            self.page = await self.context.new_page()
            self.is_running = True
            
            # Start ad skipper
            self._ad_task = asyncio.create_task(self._ad_skipper_loop())
            logger.info("Browser initialized successfully with window size 1024x768.")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            await self.reset()
            raise

    async def reset(self):
        """Reset internal state and close browser resources."""
        self.is_running = False
        if self._ad_task:
            self._ad_task.cancel()
            try:
                await self._ad_task
            except asyncio.CancelledError:
                pass
            self._ad_task = None
        
        # Close in reverse order to avoid dependency issues
        try:
            if self.page:
                try:
                    await self.page.close()
                except Exception as e:
                    logger.debug(f"Error closing page: {e}")
                self.page = None
        except Exception:
            self.page = None
                
        try:
            if self.context:
                await self.context.close()
        except Exception as e:
            logger.debug(f"Error closing context: {e}")
        finally:
            self.context = None
            
        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")
        finally:
            self.browser = None
            
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping playwright: {e}")
        finally:
            self.playwright = None
        
        logger.info("Browser resources cleaned up.")

    async def _restore_session(self):
        """Restore the last watched video and timestamp."""
        if self.state.get("last_video"):
            logger.info(f"Restoring session: {self.state['last_video']} at {self.state['timestamp']}s")
            try:
                await self.page.goto(self.state['last_video'])
                await self.page.wait_for_selector(self.selectors["video_player"], timeout=15000)
                if self.state.get("timestamp", 0) > 0:
                    # Seek after a short delay to ensure player is ready
                    await asyncio.sleep(1)
                    await self.page.evaluate(f"document.querySelector('video').currentTime = {self.state['timestamp']}")
            except Exception as e:
                logger.error(f"Error restoring session: {e}")
        else:
            logger.warning("No session to restore.")

    async def _ad_skipper_loop(self):
        """Background task to detect and skip ads."""
        logger.info("Ad skipper started.")
        while self.is_running:
            if self.page:
                try:
                    # Check for skip button
                    skip_btn = self.page.locator(self.selectors["skip_ad_btn"])
                    # Use a short timeout to prevent hanging
                    if await skip_btn.count() > 0 and await skip_btn.is_visible(timeout=500):
                        logger.info("Ad detected! Skipping...")
                        await skip_btn.click()
                        await asyncio.sleep(1)
                    
                    # Check for overlay close buttons
                    overlay_close = self.page.locator(".ytp-ad-overlay-close-button")
                    if await overlay_close.count() > 0 and await overlay_close.is_visible(timeout=500):
                         await overlay_close.click()

                except Exception as e:
                    error_str = str(e)
                    # If target closed or browser killed, stop loop gracefully
                    if any(msg in error_str for msg in ["Target closed", "Session closed", "Browser closed", "Connection lost", "WebSocket closed", "Target page, context or browser has been closed"]):
                        logger.warning(f"Browser disconnected, stopping ad skipper: {error_str}")
                        self.is_running = False
                        break
                    # For other errors, just continue
                    logger.debug(f"Ad skipper error (continuing): {error_str}")
            await asyncio.sleep(2)

    async def play_video(self, query: str):
        """Search and play a video."""
        await self.initialize()

        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                # Check if it's a URL or keyword
                if "youtube.com/watch" in query or "youtu.be/" in query:
                    url = query
                    logger.info(f"Navigating to: {url}")
                    await self.page.goto(url, wait_until="domcontentloaded")
                else:
                    # Human-like search flow: Home -> Type -> Search -> Click
                    logger.info("Opening YouTube Home...")
                    await self.page.goto("https://www.youtube.com", wait_until="domcontentloaded")
                    
                    logger.info(f"Searching for: {query}")
                    
                    # Handle potential cookie consent or other popups first if they exist
                    try:
                        consent_btn = self.page.locator("button[aria-label='Accept the use of cookies and other data for the purposes described'], button[aria-label='Accept all']")
                        if await consent_btn.count() > 0 and await consent_btn.is_visible():
                             await consent_btn.click()
                    except:
                        pass

                    # Wait for search input with fallback selectors
                    search_input = self.page.locator("input#search, input[name='search_query']").first
                    await search_input.wait_for(state="visible", timeout=15000)
                    await search_input.click()
                    await search_input.fill(query)
                    await search_input.press("Enter")
                    
                    # Wait for results
                    await self.page.wait_for_selector("ytd-video-renderer", state="visible", timeout=15000)
                    
                    # Click the thumbnail of the first video - this is often more reliable than the title link
                    first_video = self.page.locator("ytd-video-renderer").first
                    thumbnail = first_video.locator("a#thumbnail")
                    
                    # Get title for logging
                    try:
                        title_el = first_video.locator("#video-title") 
                        await title_el.wait_for(state="attached", timeout=5000)
                        title = await title_el.inner_text()
                    except:
                        title = "Unknown Video"

                    logger.info(f"Clicking video thumbnail: {title}")
                    
                    # Ensure thumbnail is clickable
                    await thumbnail.wait_for(state="visible", timeout=5000)
                    await thumbnail.click()
                    
                    # Small delay to ensure navigation starts
                    await asyncio.sleep(2)
                
                # Wait for player
                try:
                    await self.page.wait_for_selector(self.selectors["video_player"], state="attached", timeout=15000)
                except:
                    logger.warning("Video player not found immediately, trying fallback...")
                
                # Update state
                self.state["last_video"] = self.page.url
                self._save_state()
                logger.info(f"Successfully playing: {self.state['last_video']}")

            except Exception as e:
                error_str = str(e)
                if any(msg in error_str for msg in ["Target closed", "Session closed", "Browser closed", "Connection lost", "Target page, context or browser has been closed"]):
                    if attempt < max_retries:
                        logger.warning(f"Browser was closed, reinitializing (attempt {attempt + 1}/{max_retries + 1})...")
                        await self.reset()
                        await self.initialize()
                        continue
                    else:
                        logger.error(f"Browser closed and max retries exceeded: {e}")
                        await self.reset()
                        raise Exception(f"Failed to play video - browser is not responding: {e}")
                
                logger.error(f"Error playing video: {e}")
                raise

    async def control(self, action: str, value: Optional[int] = None):
        """
        Execute a control command.
        Actions: pause, resume, toggle, next, prev, mute, unmute, vol_up, vol_down, seek, skip
        """
        await self.initialize()

        try:
            if action in ["pause", "toggle"]:
                await self.page.keyboard.press("k")
            
            elif action == "resume":
                # Check if we are on a valid video page
                if "youtube.com/watch" not in self.page.url:
                    await self._restore_session()
                    await asyncio.sleep(1) # Wait for load
                    # Might need to press K if it doesn't autoplay? usually it does.
                    is_paused = await self.page.evaluate("document.querySelector('video').paused")
                    if is_paused:
                         await self.page.keyboard.press("k")
                else:
                    await self.page.keyboard.press("k")

            elif action == "next":
                await self.page.keyboard.press("Shift+N")
            
            elif action == "prev":
                await self.page.keyboard.press("Shift+P")
                
            elif action == "mute" or action == "unmute":
                await self.page.keyboard.press("m")
                
            elif action == "vol_up":
                await self.page.keyboard.press("ArrowUp")
                
            elif action == "vol_down":
                await self.page.keyboard.press("ArrowDown")
                
            elif action == "fullscreen":
                await self.page.keyboard.press("f")
                
            elif action == "minimize":
                await self.page.keyboard.press("i") # Miniplayer
            
            elif action == "seek" and value is not None:
                await self.page.evaluate(f"document.querySelector('video').currentTime = {value}")
            
            elif action == "skip" and value is not None:
                await self.page.evaluate(f"document.querySelector('video').currentTime += {value}")

            logger.info(f"Executed action: {action} {value if value else ''}")
            
            # Save state periodically on action
            if self.page:
                 self.state["last_video"] = self.page.url
                 self._save_state()

        except Exception as e:
            error_str = str(e)
            if any(msg in error_str for msg in ["Target closed", "Session closed", "Browser closed", "Connection lost", "Target page, context or browser has been closed"]):
                logger.warning(f"Browser closed during control action '{action}'. Please try again.")
                await self.reset()
                raise Exception(f"Browser was closed. Please try the action again.")

            logger.error(f"Error executing {action}: {e}")
            raise

    async def get_current_time(self):
        if self.page:
            try:
                return await self.page.evaluate("document.querySelector('video').currentTime")
            except:
                return 0
        return 0

    async def close(self):
        """Shutdown safely."""
        self.is_running = False
        if self.page:
            # Save final position
            try:
                time = await self.get_current_time()
                self.state["timestamp"] = time
                self.state["last_video"] = self.page.url
                self._save_state()
            except:
                pass
                
        await self.reset()

# Singleton instance
controller = YouTubeController()

async def get_controller():
    # Always ensure it's initialized if requested
    if not controller.is_running:
        await controller.initialize()
    return controller
