import os
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }
    }
]

try:
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "hello, what is the weather in Paris?"}],
        temperature=0.7,
        max_tokens=1500,
        top_p=0.95,
        tools=tools,
        tool_choice="auto"
    )
    print(completion.choices[0].message)
except Exception as e:
    print(f"Error: {e}")
