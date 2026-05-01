from dotenv import load_dotenv
from mem0 import MemoryClient
import logging
import json

load_dotenv()

user_name = 'Jayesh'
mem0 = MemoryClient()

def add_memory():
    messages_formatted = [
        {
            "role": "user",
            "content": "I really like Linkin Park."
        },
        {
            "role": "assistant",
            "content": "That is a good choice."
        },
        {
            "role": "user",
            "content": "I think so too."
        },
        {
            "role": "assistant",
            "content": "What is your favorite song by them?"
        },
    ]

    # ✅ user_id same variable use kiya
    mem0.add(messages_formatted, user_id=user_name)


def get_memory_by_query():
    query = f"What are {user_name}'s preferences?"

    response = mem0.search(
        query=query,
        filters={"user_id": user_name}
    )

    # ✅ actual results extract kiye
    results = response.get("results", [])

    memories = [
        {
            "memory": result.get("memory"),
            "updated_at": result.get("updated_at")
        }
        for result in results
    ]

    memories_str = json.dumps(memories, indent=2)
    print(f"Memories:\n{memories_str}")
    return memories_str


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # ✅ pehle memory add hogi
    add_memory()

    # ✅ fir search chalega
    get_memory_by_query()