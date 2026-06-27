#!/usr/bin/env python3
"""
brain/crew.py — Integração CrewAI real e robusta com 4 agentes especializados.
Compatível com Python 3.14 (monkey patch de AST) e com fallback automático local (Ollama) / nuvem (Groq).
"""
import sys
import ast

# 🚨 Monkey patch para compatibilidade com Python 3.14+ (evita erros em dependências legadas)
if sys.version_info >= (3, 14):
    if not hasattr(ast, 'NameConstant'):
        ast.NameConstant = ast.Constant
    if not hasattr(ast, 'Num'):
        ast.Num = ast.Constant
    if not hasattr(ast, 'Str'):
        ast.Str = ast.Constant

import os
from typing import Optional, List

try:
    from crewai import Crew, Agent, Task, Process
    HAS_CREW = True
except ImportError:
    HAS_CREW = False

try:
    from langchain_core.tools import tool
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

# Importações dos serviços reais da Luna
from actions.google_services import get_google
from actions.document_services import get_doc_services
from actions.system_tools import get_system_tools
from actions.browser_agent import BrowserAgent
from config import GROQ_API_KEY, GROQ_MODELS

# Lazy singleton instance
_crew_instance = None


def get_llm():
    """Retorna o LLM adequado para o CrewAI: ChatGroq (nuvem) ou ChatOllama (local)."""
    if GROQ_API_KEY.strip():
        try:
            from langchain_groq import ChatGroq
            model_name = GROQ_MODELS.get("heavy", "llama-3.3-70b-versatile")
            return ChatGroq(
                groq_api_key=GROQ_API_KEY,
                model_name=model_name,
                temperature=0.3
            )
        except Exception as e:
            print(f"[CrewAI] Erro ao carregar ChatGroq, tentando local/Ollama: {e}")
            
    # Fallback local via ChatOllama
    try:
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model="qwen2.5:7b-instruct-q4_K_M",
            base_url="http://localhost:11434",
            temperature=0.3
        )
    except Exception as e:
        print(f"[CrewAI] Erro ao carregar ChatOllama: {e}")
        return None


# ── Definição de Ferramentas Reais para os Agentes ───────────────────

# Decorator dummy se langchain não existir
if not HAS_LANGCHAIN:
    def tool(name_or_func=None):
        if callable(name_or_func): return name_or_func
        return lambda f: f
else:
    # Usa o decorator original
    pass

@tool("google_calendar_events")
def google_calendar_events(max_results: int = 5) -> str:
    """Consulta os próximos eventos do Google Calendar."""
    g = get_google()
    if g and g.available:
        return g.get_calendar_events(max_results)
    return "FALHOU: Google API indisponível."

@tool("google_unread_emails")
def google_unread_emails(max_results: int = 5) -> str:
    """Consulta os e-mails não lidos do Gmail."""
    g = get_google()
    if g and g.available:
        return g.get_unread_emails(max_results)
    return "FALHOU: Google API indisponível."

@tool("google_send_email")
def google_send_email(to: str, subject: str, body: str, attachment: str = "") -> str:
    """Envia um e-mail através do Gmail."""
    g = get_google()
    if g and g.available:
        return g.send_email(to, subject, body, attachment if attachment else None)
    return "FALHOU: Google API indisponível."

@tool("read_local_file")
def read_local_file(filepath: str) -> str:
    """Lê o conteúdo de um arquivo do workspace local."""
    return get_doc_services().read_file(filepath)

@tool("save_local_file")
def save_local_file(content: str, filepath: str) -> str:
    """Salva texto em um arquivo local no workspace."""
    return get_doc_services().save_file(content, filepath)

@tool("create_excel_spreadsheet")
def create_excel_spreadsheet(data_json: str, filename: str) -> str:
    """Cria uma planilha Excel a partir de uma lista JSON de objetos."""
    import json
    try:
        data = json.loads(data_json)
        return get_doc_services().create_excel(data, filename)
    except Exception as e:
        return f"FALHOU: Erro ao parsear JSON: {e}"

@tool("browse_the_web")
def browse_the_web(task: str) -> str:
    """Realiza navegação na web interativa para pesquisar informações ou automatizar tarefas no navegador."""
    try:
        return BrowserAgent().run(task)
    except Exception as e:
        return f"FALHOU: Erro ao rodar BrowserAgent: {e}"

@tool("get_system_diagnostic")
def get_system_diagnostic() -> str:
    """Coleta o status de hardware (CPU, RAM, Disco) do servidor."""
    return str(get_system_tools().get_system_status())

@tool("run_terminal_command")
def run_terminal_command(command: str) -> str:
    """Executa com segurança um comando bash de diagnóstico ou automação local."""
    return get_system_tools().run_bash_command(command)


def _create_agents(llm):
    """Inicializa os 4 agentes especializados reais."""
    
    prod_agent = Agent(
        role="Especialista em Produtividade e Google APIs",
        goal="Gerenciar de forma perfeita e proativa a agenda, e-mails e arquivos do usuário.",
        backstory="Você é um assistente executivo digital premium de altíssimo nível. Possui acesso nativo ao Google Calendar, Gmail e Drive.",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[google_calendar_events, google_unread_emails, google_send_email]
    )

    coder_agent = Agent(
        role="Engenheiro de Software e Documentos",
        goal="Escrever códigos robustos, ler/escrever arquivos no workspace local e manipular planilhas Excel perfeitamente.",
        backstory="Você é um desenvolvedor full-stack brilhante. Gosta de criar soluções organizadas e gerar planilhas perfeitas com Pandas e openpyxl.",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[read_local_file, save_local_file, create_excel_spreadsheet]
    )

    nav_agent = Agent(
        role="Navegador Web e Automação",
        goal="Navegar em tempo real na internet, extrair informações exatas e interagir com páginas da web.",
        backstory="Você é o 'olho' da Luna na internet. Consegue resolver problemas complexos abrindo o navegador de forma autônoma.",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[browse_the_web]
    )

    life_agent = Agent(
        role="Administrador de Sistema e Vida Prática",
        goal="Monitorar o hardware, gerenciar o servidor através do terminal bash de forma segura e apoiar a rotina geral.",
        backstory="Você é o guardião do sistema operacional PearOS. Domina comandos de shell e sabe ler logs de forma cirúrgica e segura.",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[get_system_diagnostic, run_terminal_command]
    )

    return prod_agent, coder_agent, nav_agent, life_agent


def get_crew():
    """Retorna o singleton de CrewAI configurado."""
    global _crew_instance
    if _crew_instance is None:
        llm = get_llm()
        prod, coder, nav, life = _create_agents(llm)
        
        # Tarefa inicial genérica que será ajustada dinamicamente
        task = Task(
            description="{task_description}",
            expected_output="Resposta detalhada e estruturada com base na execução das tarefas pelos agentes especialistas.",
            agent=prod
        )
        
        _crew_instance = Crew(
            agents=[prod, coder, nav, life],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )
    return _crew_instance


def run_crew_task(task_description: str) -> str:
    """Executa uma tarefa descrita de forma dinâmica através do Crew de agentes."""
    if not HAS_CREW:
        return "FALHOU: CrewAI não instalado. Peça ao usuário para rodar 'pip install crewai'."
    try:
        crew = get_crew()
        # Ajusta a descrição dinamicamente
        crew.tasks[0].description = task_description
        
        # Mapeamento dinâmico de agente ideal para a tarefa
        desc_lower = task_description.lower()
        prod, coder, nav, life = crew.agents
        
        if any(w in desc_lower for w in ["agenda", "calendario", "calendar", "email", "gmail", "enviar email", "compromisso"]):
            crew.tasks[0].agent = prod
        elif any(w in desc_lower for w in ["codigo", "python", "javascript", "excel", "planilha", "escrever arquivo", "ler arquivo", "xlsx"]):
            crew.tasks[0].agent = coder
        elif any(w in desc_lower for w in ["navegue", "site", "browser", "pesquisa", "internet", "google", "web"]):
            crew.tasks[0].agent = nav
        elif any(w in desc_lower for w in ["hardware", "cpu", "memoria", "ram", "terminal", "bash", "processos"]):
            crew.tasks[0].agent = life
        else:
            crew.tasks[0].agent = prod  # Default
            
        print(f"[CrewAI] Iniciando tarefa com o agente: {crew.tasks[0].agent.role}")
        result = crew.kickoff()
        return str(result)
    except Exception as e:
        return f"FALHOU: Erro ao executar CrewAI: {str(e)}"


if __name__ == "__main__":
    # Teste rápido manual
    print("--- Testando CrewAI localmente ---")
    print(run_crew_task("Verifique o uso de hardware do sistema através do agente correspondente."))
