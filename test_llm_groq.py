import sys
from brain.llm import LLMWrapper
from brain.agent_tools import LUNA_TOOLS
from config import MODELS

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "hello"}
]

llm = LLMWrapper()
# Forcing Groq by turning off Mistral, Gemini, OpenRouter
llm._mistral_ok = False
llm._gemini_ok = False
llm._or_ok = False
llm._groq_ok = True

print("Calling Groq...")
result = llm.generate(
    prompt=None,
    task_type="conversational",
    model=MODELS["main"],
    messages=messages,
    tools=LUNA_TOOLS
)
print("Result:")
print(result)
