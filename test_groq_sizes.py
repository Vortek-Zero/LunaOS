import os
from groq import Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

for tokens in [1000, 2000, 4000, 5000, 6000]:
    try:
        content = "word " * int(tokens * 0.7)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": content}],
            max_tokens=100
        )
        print(f"Tokens ~{tokens}: SUCCESS")
    except Exception as e:
        print(f"Tokens ~{tokens}: ERROR {str(e)[:150]}")
