import os
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

try:
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "tool", "content": "hello"}],
        temperature=0.7,
        max_tokens=1500,
        top_p=0.95
    )
    print(completion.choices[0].message)
except Exception as e:
    print(f"Error: {e}")
