"""
Generate LiveKit Token for Testing Vision
This creates a token you can use to connect to your LiveKit room with camera enabled
"""

import os
from datetime import timedelta
from dotenv import load_dotenv
from livekit import api
import sys 
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def generate_token():
    """Generate a LiveKit access token for testing"""
    
    # Get credentials from .env
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")
    
    if not all([api_key, api_secret, livekit_url]):
        print(" Error: Missing LiveKit credentials in .env file")
        print("   Required: LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL")
        return
    
    print(" Generating LiveKit Access Token...")
    print(f"   URL: {livekit_url}")
    print()
    
    # Create token
    token = api.AccessToken(api_key, api_secret)
    token.with_identity("test-user")
    token.with_name("Vision Test User")
    token.with_grants(api.VideoGrants(
        room_join=True,
        room="vision-test-room",
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    ))
    
    # Token valid for 3 years
    token.with_ttl(timedelta(days=365*3))
    
    jwt_token = token.to_jwt()
    
    with open("access_token.txt", "w", encoding="utf-8") as f:
        f.write(jwt_token)

    print(" Token Generated Successfully!")
    print()
    print("=" * 70)
    print("YOUR LIVEKIT TOKEN:")
    print("=" * 70)
    print(jwt_token)
    print("=" * 70)
    print()
    print(" How to Use This Token:")
    print()
    print("1. Go to LiveKit Playground:")
    print("   https://agents-playground.livekit.io/")
    print()
    print("2. Click 'Custom' connection")
    print()
    print("3. Enter:")
    print(f"   • URL: {livekit_url}")
    print("   • Token: (paste the token above)")
    print()
    print("4. Enable your camera and microphone")
    print()
    print("5. Click 'Connect'")
    print()
    print("6. In another terminal, run:")
    print("   python agent.py dev")
    print()
    print("7. The agent will see your camera! Test with:")
    print("   'What do you see?'")
    print("   'Kya dekh rahe ho?'")
    print()
    print(" Vision will work automatically! ")
    print()

if __name__ == "__main__":
    generate_token()
