
import livekit.agents
import pkgutil
import importlib
import sys

print("Searching for Worker class in livekit.agents...")

def search_in_module(module_name):
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        return
    except Exception:
        return

    # Check dir
    for attr in dir(mod):
        if attr == 'Worker':
            print(f"FOUND: {module_name}.Worker")
            obj = getattr(mod, attr)
            print(f"Type: {type(obj)}")
            return

    # Recurse
    if hasattr(mod, '__path__'):
        for _, subname, _ in pkgutil.iter_modules(mod.__path__):
             sys.stdout.flush()
             search_in_module(f"{module_name}.{subname}")

search_in_module('livekit.agents')
print("Search complete.")
