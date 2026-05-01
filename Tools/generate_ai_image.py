import os
import time
import aiohttp
import json
import asyncio
from datetime import datetime
from urllib.parse import quote
from livekit.agents import function_tool

_room_ctx = None

def set_room_context(room):
    global _room_ctx
    _room_ctx = room

async def send_progress(status: str, percent: int, image_url: str = None):
    if _room_ctx and _room_ctx.local_participant:
        msg = {
            "type": "IMAGE_GENERATION_PROGRESS",
            "status": status,
            "percent": percent
        }
        if image_url:
            msg['image_url'] = image_url
            
        try:
            await _room_ctx.local_participant.publish_data(json.dumps(msg).encode(), reliable=True)
        except Exception as e:
            print(f"Error broadcasting image progress: {e}")

async def download_file(url: str, output_path: str, timeout: int = 60) -> bool:
    """Fast async downloader."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return False
                data = await resp.read()
                with open(output_path, "wb") as f:
                    f.write(data)
                return True
    except:
        return False

def open_image(path: str) -> bool:
    try:
        os.startfile(path)
        return True
    except:
        return False

def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

@function_tool()
async def generate_ai_image(
    prompt: str,
    quality: str = "balanced",
    width: int = 1024,
    height: int = 1024,
    model: str = "flux"
) -> str:
    """
    ⚡ Ultra-fast AI Image Generator using Pollinations.ai
    - English prompt recommended
    - Auto filename
    - Auto-open image
    """
    t0 = time.time()

    try:
        if not prompt.strip():
            return "❌ Please enter a valid English prompt."

        await send_progress("Initializing generation parameters...", 10)

        # Quality presets
        q = {
            "fast": {"steps": 12, "cfg": 6.5},
            "balanced": {"steps": 20, "cfg": 7.2},
            "quality": {"steps": 32, "cfg": 8.0}
        }.get(quality, {"steps": 20, "cfg": 7.2})

        await send_progress("Connecting to AI synthesis engine...", 30)

        # File output location (save in Pictures/Jarvis_Images)
        pictures_dir = os.path.join(os.path.expanduser('~'), 'Pictures', 'Jarvis_Images')
        os.makedirs(pictures_dir, exist_ok=True)

        clean = "".join(c for c in prompt[:20] if c.isalnum() or c in " _").strip() or "image"
        filename = f"{clean}_{datetime.now().strftime('%H%M%S')}.png"
        output_path = os.path.join(pictures_dir, filename)

        await send_progress("Synthesizing image grid...", 50)

        # API URL
        encoded = quote(prompt)
        # Using enhanced default pipeline instead of hardcoded steps which causes blur/failure
        params = f"width={width}&height={height}&nologo=true&enhance=true"
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?{params}"

        await send_progress("Applying final quality enhancements...", 75)

        # Download image
        if not await download_file(image_url, output_path, timeout=40):
            await send_progress("Image generation failed", 100)
            return "❌ Failed to generate image. Try changing your prompt or reducing quality."

        await send_progress("Saving to file manager...", 90)

        # Validate image size
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1500:
            await send_progress("Failed validating file", 100)
            return "❌ Image generation failed — received invalid/empty file."

        dt = time.time() - t0
        
        # Local relative path to image to show inside electron app overlay if possible
        # We might not be able to easily show local files in electron's UI unless via file:// 
        # but pollination returns the image immediately, so we can pass the URL.
        await send_progress("Image generated successfully!", 100, image_url=image_url)
        await asyncio.sleep(1) # Let UI show 100% for a brief moment
        
        # Auto-open
        opened = open_image(output_path)

        return f"""
🎉 **Image Generated Successfully!**

📝 **Prompt:** {prompt}
⚡ **Quality:** {quality}
📏 **Size:** {width}×{height}
⏱️ **Time:** {dt:.1f}s
📦 **File Size:** {format_size(os.path.getsize(output_path))}
📁 **Saved at:** `{output_path}`
{ '🖼️ Opened Automatically!' if opened else '⚠️ Could not auto-open, but file is saved.' }
        """.strip()

    except Exception as e:
        await send_progress(f"Error: {str(e)}", 100)
        return f"❌ Generation failed: {str(e)}"
