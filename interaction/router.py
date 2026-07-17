#!/usr/bin/env python3
"""
router.py — Roteador inteligente com conselho de IAs.
Recebe um objetivo, consulta o registry, e usa múltiplos modelos
para decidir a melhor ferramenta e estratégia.

Fluxo:
  1. Registry → ferramentas candidatas por categoria
  2. Conselho de IAs → cada modelo propõe um plano
  3. Agregação → vota na melhor abordagem
  4. Execução → tenta ferramentas em ordem (fallback)
  5. Verificação → confirma sucesso
  6. Memória → aprende para a próxima
"""

import json

from interaction.registry import get_registry
from interaction.verifier import Verifier


class Router:
    def __init__(self, llm=None):
        self._llm = llm
        self._registry = get_registry()
        self._verifier = Verifier()
        self._council_cache = {}

    def set_llm(self, llm) -> None:
        self._llm = llm

    def resolve(self, goal: str, context: dict = None) -> dict:
        """
        Ponto de entrada principal.
        Recebe um objetivo e retorna o resultado da melhor estratégia.
        """
        context = context or {}
        category = self._classify_goal(goal)

        candidates = self._registry.find(category) + self._registry.find("generic")
        if not candidates:
            candidates = self._registry.all_tools()

        if not candidates:
            return {"status": "error", "error": "Nenhuma ferramenta disponível", "goal": goal}

        plan = self._council_deliberate(goal, candidates, context)

        for approach in plan["approaches"]:
            tool = self._registry.find_by_name(approach.get("tool"))
            if not tool:
                continue
            if not tool.available():
                continue

            result = tool.execute({**context, "goal": goal, **approach.get("params", {})})
            success = self._verifier.check(result, goal)

            if success:
                self._learn(goal, approach, result)
                return {
                    "status": "success",
                    "tool": tool.name,
                    "data": result.data,
                    "approach": approach,
                    "plan": plan,
                }

        return {
            "status": "failed",
            "goal": goal,
            "plan": plan,
            "error": "Todas as abordagens falharam",
        }

    def _classify_goal(self, goal: str) -> str:
        goal_lower = goal.lower()
        if any(
            w in goal_lower
            for w in ["abrir", "navegar", "youtube", "site", "http", "www", "browser", "pesquisar", "baixar"]
        ):
            return "browser"
        if any(w in goal_lower for w in ["terminal", "bash", "comando", "executar", "rodar", "instalar", "linux"]):
            return "system"
        if any(w in goal_lower for w in ["arquivo", "criar", "escrever", "ler", "salvar", "editar"]):
            return "file"
        if any(w in goal_lower for w in ["api", "requisição", "curl", "http"]):
            return "api"
        return "generic"

    def _council_deliberate(self, goal: str, candidates: list, context: dict) -> dict:
        """
        Conselho de IAs: múltiplos modelos deliberam sobre a melhor abordagem.
        Se não tiver LLM disponível, usa heurística simples.
        """
        if not self._llm:
            return self._heuristic_plan(goal, candidates)

        tools_desc = "\n".join(f"  - {t.name}: {t.description} (prioridade {t.priority})" for t in candidates)

        prompt = f"""Objetivo: {goal}

Ferramentas disponíveis:
{tools_desc}

Contexto: {json.dumps(context, ensure_ascii=False)}

Tarefa: Crie um plano de ação com as ferramentas acima.
Para cada abordagem, especifique:
1. tool: nome da ferramenta
2. params: parâmetros para execução
3. rationale: por que esta abordagem foi escolhida

Retorne APENAS JSON no formato:
{{"approaches": [{{"tool": "...", "params": {{}}, "rationale": "..."}}]}}"""

        try:
            from brain.llm import get_llm

            llm = get_llm()
            raw = llm.generate(
                prompt=prompt,
                task_type="planning",
                model="puter/o3",
                max_retries=1,
            )
            if raw:
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
                plan = json.loads(cleaned)
                if "approaches" in plan:
                    return plan
        except Exception:
            pass

        return self._heuristic_plan(goal, candidates)

    def _heuristic_plan(self, goal: str, candidates: list) -> dict:
        """Plano heurístico quando o conselho de IAs não está disponível."""
        approaches = []
        for tool in candidates:
            if tool.available():
                params = self._extract_params(goal, tool)
                approaches.append(
                    {
                        "tool": tool.name,
                        "params": params,
                        "rationale": f"Tentativa via {tool.name}",
                    }
                )
        return {"approaches": approaches}

    def _extract_params(self, goal: str, tool) -> dict:
        """Extrai parâmetros apropriados para cada ferramenta baseado no objetivo."""
        base = {"goal": goal}

        if tool.name == "bash":
            cmd = goal
            for prefix in ["executar ", "execute ", "rodar ", "roda ", "comando ", "bash "]:
                if cmd.lower().startswith(prefix):
                    cmd = cmd[len(prefix) :]
            base["command"] = cmd.strip()

        elif tool.name == "dom":
            goal_lower = goal.lower()
            if any(w in goal_lower for w in ["abrir", "navegar", "http", "www", "youtube", "site"]):
                for w in ["abrir ", "navegar para ", "navegar até ", "vai para ", "abra "]:
                    if goal_lower.startswith(w):
                        url = goal[len(w) :].strip()
                        break
                else:
                    url = goal
                if not url.startswith("http"):
                    known_sites = {
                        "youtube": ".com",
                        "google": ".com",
                        "gmail": ".com",
                        "github": ".com",
                        "facebook": ".com",
                        "twitter": ".com",
                        "x": ".com",
                        "instagram": ".com",
                        "linkedin": ".com",
                        "reddit": ".com",
                        "twitch": ".tv",
                        "spotify": ".com",
                        "netflix": ".com",
                        "amazon": ".com",
                        "stackoverflow": ".com",
                    }
                    if url in known_sites:
                        url = "https://www." + url + known_sites[url]
                    elif any(url.endswith("." + s) for s in ["com", "org", "net", "io", "gov", "edu", "br", "pt"]):
                        url = "https://" + url
                    elif " " not in url:
                        url = "https://www." + url + ".com"
                    else:
                        url = "https://www.google.com/search?q=" + url.replace(" ", "+")
                base["action"] = "navigate"
                base["url"] = url
            elif any(w in goal_lower for w in ["pesquisar", "buscar", "pesquisa", "busca", "procura"]):
                query = goal
                for w in ["pesquisar por ", "pesquisar ", "buscar por ", "buscar ", "procura por ", "procure "]:
                    if goal_lower.startswith(w):
                        query = goal[len(w) :].strip()
                        break
                base["action"] = "search"
                base["search_query"] = query
            elif any(w in goal_lower for w in ["clicar", "clique", "clica", "click"]):
                target = goal
                for w in ["clicar em ", "clique em ", "clica em ", "clique no ", "clique na ", "click "]:
                    if goal_lower.startswith(w):
                        target = goal[len(w) :].strip()
                        break
                base["action"] = "click"
                base["selector"] = target
            else:
                base["action"] = "navigate"
                base["url"] = "https://www.google.com"

        elif tool.name == "python":
            code = goal
            for w in ["execute python: ", "rodar python: ", "python: "]:
                if goal.lower().startswith(w):
                    code = goal[len(w) :].strip()
                    break
            base["code"] = code

        elif tool.name == "api":
            base["method"] = "GET"
            base["url"] = goal

        return base

    def _learn(self, goal: str, approach: dict, result) -> None:
        """Aprende com a experiência para melhorar decisões futuras."""
        try:
            from learning.strategy_memory import StrategyMemory

            memory = StrategyMemory()
            memory.record(
                goal=goal,
                tool=approach.get("tool", ""),
                params=approach.get("params", {}),
                success=True,
            )
        except Exception:
            pass
