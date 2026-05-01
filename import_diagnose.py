import sys
print('python', sys.executable)
try:
    import google
    print('google', getattr(google, '__file__', None), getattr(google, '__path__', None))
except Exception as e:
    print('google import failed', type(e).__name__, e)
try:
    import google.genai
    print('google.genai', getattr(google.genai, '__file__', None))
except Exception as e:
    print('google.genai import failed', type(e).__name__, e)
try:
    import livekit.plugins.google
    print('livekit.plugins.google', getattr(livekit.plugins.google, '__file__', None))
except Exception as e:
    print('livekit.plugins.google import failed', type(e).__name__, e)
