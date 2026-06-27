#!/usr/bin/env python3
"""
brain/agno_agent.py — Integração com Agno (anteriormente Phidata) para agentes de alta performance.
"""
import sys
import os

# Ajusta path para importar Agno da pasta libs
AGNO_PATH = os.path.abspath(os.path.join(os.getcwd(), "agno/libs/agno"))
if AGNO_PATH not in sys.path:
    sys.path.append(AGNO_PATH)

try:
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    from agno.models.google import Gemini
    from agno.models.groq import Groq
    HAS_AGNO = True
except ImportError:
    HAS_AGNO = False

from config import GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODELS

def get_agno_agent(name: str = "Luna-Specialist", instructions: list = None):
    if not HAS_AGNO:
        return None

    # Usa Groq como padrão para velocidade ou Gemini para visão/contexto longo
    if GROQ_API_KEY:
        model = Groq(id=GROQ_MODELS.get("heavy", "llama-3.3-70b-versatile"), api_key=GROQ_API_KEY)
    elif GEMINI_API_KEY:
        model = Gemini(id="gemini-2.0-flash", api_key=GEMINI_API_KEY)
    else:
        return None

    return Agent(
        name=name,
        model=model,
        instructions=instructions or ["Você é uma extensão especializada da Luna."],
        markdown=True
    )

def run_agno_task(task: str) -> str:
    agent = get_agno_agent(instructions=["Você é um agente executor sênior da Luna. Resolva a tarefa de forma direta."])
    if not agent:
        return "FALHOU: Agno não configurado ou sem API Keys."
    
    response = agent.run(task)
    return response.content

if __name__ == "__main__":
    if HAS_AGNO:
        print("Agno importado com sucesso!")
        # print(run_agno_task("Diga olá mundo"))
    else:
        print("Agno não encontrado.")
