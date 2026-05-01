import logging
from livekit.agents import function_tool
import aiohttp
import asyncio

# Configure logging
logger = logging.getLogger(__name__)

@function_tool()
async def get_weather(city: str) -> str:
    """
    Fetches current weather conditions for a specified city in Hindi/English.
    
    Args:
        city (str): The city name to get weather for (e.g., "Delhi")
        
    Returns:
        str: Formatted weather string with temperature and wind speed
        
    Behavior:
        1. First tries Open-Meteo geocoding API
        2. Falls back to OpenStreetMap if needed
        3. Returns temperature (°C) and wind speed (km/h)
        
    Example:
        "Delhi का वर्तमान तापमान है 32°C और पवन की गति है 12 km/h।"
    
    """
    try:
        print(f"🌤️ Getting weather for: {city}")
        
        async with aiohttp.ClientSession() as session:
            # Get location coordinates
            async with session.get(
                f"https://geocoding-api.open-meteo.com/v1/search?name={city}",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                geo_data = await response.json()

            if not geo_data.get("results"):
                async with session.get(
                    f"https://nominatim.openstreetmap.org/search?q={city}&format=json",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    geo_data = await response.json()
                    if not geo_data:
                        return f"क्षमा करें, मैं स्थान नहीं ढूंढ पाया: {city}."

            location = geo_data[0] if isinstance(geo_data, list) else geo_data["results"][0]
            
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={location.get('lat', location.get('latitude'))}&"
                f"longitude={location.get('lon', location.get('longitude'))}&"
                f"current_weather=true"
            )
            
            async with session.get(weather_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                weather_data = await response.json()

            if "current_weather" in weather_data:
                current = weather_data["current_weather"]
                location_name = location.get('display_name', location.get('name', city))
                result = (
                    f"{location_name} का वर्तमान तापमान है {current['temperature']}°C "
                    f"और पवन की गति है {current['windspeed']} km/h।"
                )
                print(f"✅ Weather result: {result}")
                return result
            
            return f"मौसम की जानकारी प्राप्त करने में असमर्थ: {city}"
    except Exception as e:
        logger.error(f"मौसम त्रुटि: {e}")
        return "मौसम सेवा अस्थायी रूप से अनुपलब्ध है। कृपया बाद में प्रयास करें।"
