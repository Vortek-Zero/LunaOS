# Recursos Faltantes e Evolução da Luna

Este documento lista as ideias de melhorias do sistema Luna, organizadas pelo que já foi implementado e pelo planejamento futuro.

---

## ✅ Implementados na Versão 1.4

### 🔄 1. Reflexão e Auto Avaliação
- **Como funciona:** A Luna possui uma etapa de autoavaliação (Reflexão) antes de retornar respostas, medindo se o objetivo foi cumprido, analisando falhas de ferramentas e ajustando a rota caso necessário.
- **Integração:** Integrado no `luna_core.py` no loop de ReAct.

### ⚡ 2. Event Bus
- **Como funciona:** O Event Bus (`brain/event_bus.py`) fornece um barramento de eventos assíncronos para comunicar diferentes módulos (ex: execução de ferramenta dispara eventos) em paralelo.
- **Integração:** Ferramentas publicam no `EventBus` após execução. Módulos assinam eventos para reagir assincronamente.

### 📚 3. Aprendizado Automático de Hábitos
- **Como funciona:** O `brain/habit_learner.py` escaneia padrões de uso (ex: uso do Firefox, períodos noturnos) do log de atividades para inferir novos hábitos automaticamente.
- **Integração:** Roda periodicamente pelo `daily_routine.py` e insere hábitos no `user_model.py`.

### 📦 4. Memória Hierárquica
- **Como funciona:** O coordenador em `brain/hierarchical_memory.py` filtra as camadas de Memória Curta, Episódica, Semântica, Perfil e Objetivos para injetar no LLM sem poluir o contexto.
- **Integração:** Substituiu a geração de contexto isolado, consolidando episódios na memória vetorial do ChromaDB.

### 🤝 5. Iniciativa e Proatividade Real
- **Como funciona:** O motor de proatividade (`brain/proactivity.py`) sugere ações baseadas no horário e hábitos, como oferecer briefing pela manhã ou montar o setup à noite.
- **Integração:** Integrado às rotinas de background, gera notificações desktop e fala (via TTS) se a voz estiver ativa.

---

## ✅ Implementados na Versão 1.3.2

### 🧠 1. Memória Episódica
- O sistema registra as interações na forma de "experiências" (`brain/episodic_memory.py`).

### 🧠 2. Memória Semântica Conectada
- Integração com banco de dados vetorial local (ChromaDB) via `MemoryRAG`.

### 🎯 3. Objetivos Permanentes
- O arquivo `config/goals.json` armazena os objetivos permanentes do usuário com prioridades e status.

### 📋 4. Planner Separado
- O `brain/planner.py` gera um plano estratégico estruturado que guia o executor das ferramentas.

### 👤 5. Perfil Dinâmico / Modelo Interno do Usuário
- O `brain/user_model.py` extrai informações de novos aprendizados, hobbies e habilidades diretamente da conversa.

---

## 🚀 Planejamento Futuro (O que sobrou)

### 🕸️ 1. Knowledge Graph
- **Ideia:** Conectar entidades de forma gráfica (Pessoa → Programador → Python → Projeto Calu). Essencial para relacionamentos e representação de conhecimento complexo.

### 🤖 2. Multiagentes Especialistas
- **Ideia:** Divisão de papéis interna entre subagentes especializados (Planner, Coder, Research, Vision, Automation).

### 🌍 3. World Model
- **Ideia:** Mapear os periféricos e dispositivos do usuário (PC, monitor, lâmpadas, calendários) como entidades ricas e interconectadas com estados.

### 📅 4. Timeline da Vida
- **Ideia:** Entender a linha do tempo do usuário ao longo dos anos (estudos, faculdade, projetos, evolução profissional).

### 🔌 5. Sistema de Plugins Extensível
- **Ideia:** Permitir que terceiros adicionem integrações modulares (Discord, Home Assistant, etc.).

---

## 🎯 Próxima Prioridade Sugerida
- Implementar **Multiagentes Especialistas** para refatorar as ações e criar divisões de responsabilidade mais claras, ou **Knowledge Graph** para escalar as relações entre ferramentas, projetos e contatos.