import os
from groq import Groq
from brain.agent_tools import LUNA_TOOLS

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

try:
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=300,
        tools=LUNA_TOOLS,
        tool_choice="auto"
    )
    print("SUCCESS!")
    print(completion.choices[0].message)
except Exception as e:
    print(f"Error: {e}")
