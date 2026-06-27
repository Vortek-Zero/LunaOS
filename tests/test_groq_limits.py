import os
from groq import Groq
from brain.agent_tools import LUNA_TOOLS

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

models = [
    "llama3-8b-8192", "llama3-70b-8192",
    "llama-3.3-70b-versatile", "mixtral-8x7b-32768",
    "gemma2-9b-it"
]
for model in models:
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            tools=LUNA_TOOLS,
            tool_choice="auto"
        )
        print(f"{model} SUCCESS")
    except Exception as e:
        print(f"{model} ERROR: {e}")
