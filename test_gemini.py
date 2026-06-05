import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")

try:
    response = model.generate_content("Hello")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
