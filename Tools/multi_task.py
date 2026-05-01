
import logging
import asyncio
from livekit.agents import function_tool

@function_tool
def execute_multi_task(tasks: list[str]):
    """
    Execute multiple sequential tasks or instructions.
    
    This tool allows the execution of a list of natural language instructions 
    in a sequence. It is useful for breaking down complex requests into 
    simpler steps.

    Args:
        tasks: A list of natural language instructions (strings) to execute in order.
               Example: ["Open notepad", "Type message 'Hello'", "Save file"]
    """
    logging.info(f"Executing multi-task sequence: {tasks}")
    results = []
    
    # Current implementation is a placeholder that logs the intent.
    # To fully implement this, we would need access to the agent's main loop 
    # or a way to dispatch these instructions back to the LLM/tool executor.
    
    results.append(f"Received {len(tasks)} tasks.")
    
    for i, task in enumerate(tasks):
        logging.info(f"Processing task {i+1}: {task}")
        # Logic to execute task would go here.
        # potentially: await process_instruction(task)
        results.append(f"Task {i+1}: '{task}' - Acknowledged.")
        
    return "\n".join(results)
