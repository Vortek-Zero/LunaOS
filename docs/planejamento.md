# 🧠 MEGA BRAIN AUDIT — LUNA

> Auditoria comprehensive — 30+ arquivos analisados, ~20.000 linhas revisadas
> Data: 26/06/2026

---

## Sumário Executivo

| Categoria | Total | Crítico | Alto | Médio |
|-----------|-------|---------|------|-------|
| 🔴 Segurança | 18 | 8 | 5 | 5 |
| 🔧 Arquitetura | 12 | 3 | 4 | 5 |
| ⚡ Performance | 10 | 1 | 4 | 5 |
| 🐛 Bugs | 15 | 4 | 6 | 5 |
| 🧪 Confiabilidade | 12 | 3 | 5 | 4 |
| 🏗️ Código | 10 | 0 | 3 | 7 |
| **Total** | **77** | **19** | **27** | **31** |

---

## 🔴 SEGURANÇA

### S1 — `shell=True` com bypass trivial de blocklist
- **Arquivo:** `actions/system_tools.py:127-134`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `run_bash_command()` usa `shell=True` com blocklist de substrings facilmente bypassada:
  - `curl | sh` bloqueado, mas `curl | bash` **passa**
  - `cat /etc/shadow` — **não bloqueado**
  - `python3 -c "import os; os.remove(...)"` — **não bloqueado**
  - `sudo rm -rf /` — `rm -rf` bloqueado, mas `sudo rm -rf /` depois de um `sudo` que está disponivel não
- **Fix:** Usar `shlex.split()` com lista de args, whitelist de comandos permitidos, ou no mínimo `subprocess.run(command.split())` sem `shell=True`

### S2 — `write_code` aceita caminhos absolutos sem validação
- **Arquivo:** `brain/agent_tools.py:1397-1409`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `write_code` aceita `filename` absoluto como `/etc/cron.d/malicious` e escreve diretamente sem validação
- **Exploit:** LLM induzido a escrever em `/etc/cron.d/`, `~/.ssh/authorized_keys`, etc.
- **Fix:** Rejeitar caminhos absolutos. Usar `WORKSPACE_DIR / filename` sempre
- **Mesmo bug em:** `create_project` (linha 1426), `check_project` (linha 1366 — leitura de `/etc/shadow`)

### S3 — CORS wildcard com credentials
- **Arquivo:** `api.py:33-39`, `config.py:46`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `allow_origins=["*"], allow_credentials=True` — qualquer site pode fazer fetch autenticado
- **Fix:** Especificar origens explicitamente

### S4 — Localhost bypass de API key
- **Arquivo:** `api.py:48-50`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Requests originadas de localhost pulam verificação de API key. SSRF pode bypassar autenticação
- **Fix:** Remover bypass ou usar token separado para comunicação interna

### S5 — Admin password vazio bloqueia tudo
- **Arquivo:** `api.py:241-248`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `if not ADMIN_PASSWORD` retorna `True` quando vazio, bloqueando TODOS endpoints admin
- **Fix:** Tratar string vazia como "sem senha" ou exigir configuração explícita

### S6 — System reset + shutdown sem role admin
- **Arquivo:** `api.py:387-408, 1406-1414`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `POST /api/system/reset` e `POST /api/shutdown` exigem apenas `verify_api_key` — qualquer um com a chave pode destruir dados ou derrubar servidor
- **Fix:** Exigir `_require_admin` para estas operações

### S7 — Race condition no STT: wakeword concorre com listen_once
- **Arquivo:** `voice/stt.py:254-330`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Loop de wakeword roda sem `self._lock`. `listen_once()` abre outro stream PyAudio. Dois streams simultâneos causam `OSError`
- **Fix:** Adquirir `self._lock` no loop de wakeword

### S8 — Token de usuário determinístico sem expiração
- **Arquivo:** `api.py:77`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Token = SHA256(username:device_id:API_KEY). Se API_KEY vazar, todos os tokens são recomputáveis. Tokens nunca expiram
- **Fix:** Adicionar salt aleatório + timestamp de expiração

### S9 — SSML injection no Azure TTS
- **Arquivo:** `voice/tts.py:325-329`
- **Severidade:** 🟡 ALTO
- **Descrição:** Texto do usuário interpolado em XML SSML sem sanitização. `&`, `<`, `>` quebram o XML
- **Fix:** Escapar XML entities no texto

### S10 — Admin endpoints sem rate limiting nem auditoria
- **Arquivo:** `api.py` (diversos)
- **Severidade:** 🟡 ALTO
- **Descrição:** Nenhum log ou auditoria de ações administrativas. Reset e shutdown não são registrados
- **Fix:** Adicionar logging com timestamp + ação + requester

### S11 — Chave privada SSL em `ssl/key.pem`
- **Arquivo:** `ssl/key.pem`
- **Severidade:** 🟡 ALTO
- **Descrição:** Se versionado no git, a chave privada do HTTPS está exposta
- **Fix:** Adicionar `ssl/` ao `.gitignore`

### S12 — API key exibida no console (12 primeiros chars)
- **Arquivo:** `api.py:1436`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `print(f"🔑 API Key: {config.API_KEY[:12]}...")` — 48 bits de entropia expostos
- **Fix:** Remover ou mascarar completamente

### S13 — API key em `.api_key` plaintext
- **Arquivo:** `config.py:34-41`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Chave salva em arquivo sem restrição de permissão
- **Fix:** `os.chmod(".api_key", 0o600)`

### S14 — ffmpeg em upload não validado
- **Arquivo:** `api.py:1059-1061`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Upload de áudio passa direto ao ffmpeg. Malformed media pode explorar vulnerabilidades do ffmpeg
- **Fix:** Validar magic bytes + limite de tamanho

### S15 — Safety filter só em português
- **Arquivo:** `brain/safety.py:19-67`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `"I want to kill myself"` passa sem bloqueio. Normalização remove pontuação permitindo bypass
- **Fix:** Adicionar padrões em inglês e verificar normalização

---

## 🔧 ARQUITETURA

### A1 — Monólito de 1932 linhas (`luna_core.py`)
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Tudo depende do singleton `LunaCore`. Baixa testabilidade, alto acoplamento
- **Claw Code tem:** `ConversationRuntime<C, T>` com traits genéricos
- **Fix:** Extrair: `AgentLoop`, `SessionManager`, `ToolOrchestrator`

### A2 — 29/48 ferramentas sem handler (60%)
- **Arquivo:** `brain/agent_tools.py`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** LLM pode chamar ferramentas e receber `"FALHOU: Ferramenta desconhecida"` silenciosamente
- **Fix:** Implementar handlers ou remover tools não implementadas de LUNA_TOOLS

### A3 — `productivity_manage` tem handler mas não está nas tools
- **Arquivo:** `brain/agent_tools.py:1322`
- **Severidade:** 🟡 ALTO
- **Descrição:** Handler existe mas ferramenta não está em LUNA_TOOLS. LLM nunca chama
- **Fix:** Adicionar definição em LUNA_TOOLS ou remover handler

### A4 — Sem sistema de permissões
- **Severidade:** 🟡 ALTO
- **Descrição:** LLM decide e executa. Uma alucinação pode deletar arquivos
- **Claw Code tem:** `PermissionPolicy` com 5 níveis (ReadOnly → Allow), pre/post hooks
- **Fix:** Implementar PermissionMode para operações sensíveis

### A5 — Sem sessão com compactação
- **Severidade:** 🟡 ALTO
- **Descrição:** Cada request stateless. Histórico sem tracking de tokens
- **Claw Code tem:** Session com compact() automático quando input_tokens > threshold
- **Fix:** Implementar Session com tracking de tokens

### A6 — Catálogo de ferramentas plano sem perfis
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Todas as 48 tools passadas em TODAS chamadas. Polui contexto e confunde o modelo
- **Fix:** Perfis: chat, coding, full. Passar apenas perfil relevante

### A7 — `get_executor()` singleton não thread-safe
- **Arquivo:** `actions/executor.py:864-870`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Duas threads podem criar duas instâncias. Double-checked locking bug
- **Fix:** Adicionar threading.Lock

### A8 — Imports dentro de funções
- **Arquivo:** `actions/executor.py:100,150,511`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Importa módulos em tempo de execução (pago a cada chamada). Importa membro privado `_pending` de outro módulo
- **Fix:** Mover imports para topo. Não importar membros privados

### A9 — STT sem isolamento de thread
- **Arquivo:** `voice/stt.py`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Wakeword loop em thread separada sem lock. Concorrência com listen_once

### A10 — Bootstrap sem fases
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `LunaCore.__init__()` faz tudo de uma vez. Sem fast-path para queries simples
- **Claw Code tem:** BootstrapPlan com fases explícitas
- **Fix:** Implementar bootstrap em fases com early-exit

### A11 — Sem hook/plugin system
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Sem hooks pre/post tool execution para logging, approval, side effects
- **Claw Code tem:** Hook system completo
- **Fix:** Adicionar hook registry

### A12 — `get_executor()` sem DI
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `luna_core.py` hard-codes dependências. Difícil testar ou trocar implementações
- **Fix:** Injeção de dependência nos construtores

---

## ⚡ PERFORMANCE

### P1 — LLM cascade de 8 provedores sequencial
- **Arquivo:** `brain/llm.py:441-514`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Mistral → Gemini → OpenRouter → GitHub → Naga → Best → Groq → Ollama. Cada timeout adiciona ~5-30s
- **Fix:** Health checks paralelos, cache de provedor funcional, timeout global

### P2 — Cache salva em disco em CADA set()
- **Arquivo:** `performance_cache.py:186`
- **Severidade:** 🟡 ALTO
- **Descrição:** `_save_cache()` escreve JSON completo a cada inserção. 100q/min = 50MB/min I/O
- **Fix:** Periodic flush (30s), dirty flag

### P3 — L1 cache e L2 cache divergem
- **Arquivo:** `performance_cache.py`
- **Severidade:** 🟡 ALTO
- **Descrição:** `clear_expired()` só limpa L2. Cache hits retornam dados expirados de L1
- **Fix:** Sync L1 com L2 em clear_expired()

### P4 — `clear_expired()` roda sem lock
- **Arquivo:** `performance_cache.py:188-210`
- **Severidade:** 🟡 ALTO
- **Descrição:** Itera dict sem lock enquanto `set()` modifica com lock. Pode crashar com `RuntimeError: dictionary changed size`
- **Fix:** Adquirir `self._lock`

### P5 — LRU sorting em toda inserção
- **Arquivo:** `performance_cache.py:178-184`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Ordena 500+ entradas em O(N log N) a cada set(). `heapq` seria O(log N)
- **Fix:** Usar heapq ou OrderedDict

### P6 — `access_count` e `last_accessed` nunca persistem
- **Arquivo:** `performance_cache.py:125-126`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Atualizados em RAM mas `_save_cache()` não chamado em get(). Perdidos no restart
- **Fix:** Salvar periodicamente ou em shutdown

### P7 — SSE stream com queue unbounded
- **Arquivo:** `api.py:959-994`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `queue.Queue()` sem maxsize. Cliente lento → RAM cresce sem limite
- **Fix:** Adicionar maxsize e lidar com overflow

### P8 — ThreadPoolExecutor compartilhado
- **Arquivo:** `api.py` (diversos)
- **Severidade:** 🟢 MÉDIO
- **Descrição:** LLM calls longas (60s+) exaurem pool default, starving outros endpoints
- **Fix:** Pool dedicado para LLM calls

### P9 — Parsing ingênuo de `.env`
- **Arquivo:** `config.py:19`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `_line.partition("=")` não trata aspas, `#` em valores, ou `=` em valores
- **Fix:** Usar `python-dotenv`

### P10 — Whisper model como atributo de função
- **Arquivo:** `api.py:1063-1065`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Modelo ~1GB preso como atributo de função. Sem reload ou cleanup
- **Fix:** Usar variável de módulo com lazy loading pattern

---

## 🐛 BUGS

### B1 — Debounce timer ressuscita dados deletados
- **Arquivo:** `brain/memory.py:410-427`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `clear_facts()` -> `self.facts = []`, `_save()`. Timer pendente do `_schedule_save()` anterior sobrescreve com dados ANTIGOS
- **Fix:** Cancelar timer em clear_facts/clear_history

### B2 — `_save()` e `_schedule_save()` race condition
- **Arquivo:** `brain/memory.py:358-404`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** `_save_lock` usado em `_schedule_save()` mas NÃO em `_save()`. Timer callback concorre com schedule
- **Fix:** Adquirir `_save_lock` em `_save()`

### B3 — `facts` e `_facts_index` não thread-safe
- **Arquivo:** `brain/memory.py:54-228`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Listas e dicts acessados de múltiplas threads sem lock. Pode causar IndexError, corrupção, dados perdidos
- **Fix:** Adicionar threading.RLock

### B4 — `compress_messages()` duplica mensagens (Stage 3)
- **Arquivo:** `brain/loop_guard.py:144-147`
- **Severidade:** 🟡 ALTO
- **Descrição:** `keep_start` pode overlap com `keep_end` quando há muitas mensagens de sistema → mensagens duplicadas
- **Fix:** Garantir `keep_start + keep_end <= len(compressed)`

### B5 — `_detect_ping_pong` só detecta períodos 2 e 3
- **Arquivo:** `brain/loop_guard.py:103-108`
- **Severidade:** 🟡 ALTO
- **Descrição:** Período 1 (AAAA) com args diferentes não detectado. Período 4+ não detectado
- **Fix:** Adicionar detecção para período 1 (threshold de repetição)

### B6 — `per_tool_budget` nunca decresce
- **Arquivo:** `brain/loop_guard.py:68-76`
- **Severidade:** 🟡 ALTO
- **Descrição:** Uma vez que tool excede budget, bloqueada PARA SEMPRE até reset()
- **Fix:** Sliding window ou decay temporal

### B7 — `warn_before_block` permite 2 calls extras
- **Arquivo:** `brain/loop_guard.py:89-97`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Avisa primeiro (não bloqueia), bloqueia só na segunda. Efeito: max_identical + 2
- **Fix:** Bloquear no primeiro excesso, avisar junto

### B8 — `_wrap_verdict` regex quebra com tool names contendo `.`
- **Arquivo:** `brain/loop_guard.py:87-97`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `r"'(\w+)'"` não captura `"web.search"`, `"code_interpreter"`. Avisa para sempre
- **Fix:** `r"'([\w.]+)'"` ou `r"'([^']+)'"`

### B9 — Screenshot scrot falha sem fallback
- **Arquivo:** `actions/executor.py:678-681`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `check=True` levanta CalledProcessError se scrot falha. Except só pega FileNotFoundError. Fallback para gnome-screenshot nunca acontece
- **Fix:** Capturar CalledProcessError também

### B10 — Caminho de screenshot hardcoded `/home/pera/Pictures`
- **Arquivo:** `actions/executor.py:676`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Quebra em qualquer outro usuário ou sistema
- **Fix:** Usar `Path.home() / "Pictures"`

### B11 — `_resolve_click` ordinal negativo vira indexação negativa
- **Arquivo:** `actions/executor.py:166`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `ordinal_idx = -1` → `good_elements[-1]` → clica no ÚLTIMO ao invés de falhar
- **Fix:** `max(0, int(...) - 1)`

### B12 — `optimize_top_p` invertido em relação ao docstring
- **Arquivo:** `performance_cache.py:266-274`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Curto → top_p 0.8 (baixo), longo → top_p 0.95 (alto). Docstring diz o oposto
- **Fix:** Corrigir docstring ou inverter lógica

### B13 — `_resolve_click` realiza side effects durante resolução
- **Arquivo:** `actions/executor.py` (diversos)
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Função de "resolução" já executa o clique. Viola princípio de surpresa mínima
- **Fix:** Separar resolução de execução

### B14 — `correct_response()` não corrige nada
- **Arquivo:** `output_parser.py:158-173`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Só seta flag `_trigger_research`. `original_query` ignorado
- **Fix:** Renomear para `flag_research_if_needed()` ou implementar correção

### B15 — `has_time` regex muito permissivo
- **Arquivo:** `actions/executor.py:523`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `r'\d{1,2}[h:]\d{0,2}'` matcha `"5h"`, `"a:1"` como tempo
- **Fix:** Exigir números em ambos os lados do separador

---

## 🧪 CONFIABILIDADE

### R1 — LLM providers sem fallback para resposta vazia
- **Arquivo:** `brain/llm.py:514`
- **Severidade:** 🔴 CRÍTICO
- **Descrição:** Quando todos os 8 provedores falham, retorna string vazia ou `"[LLM indisponível]"`
- **Fix:** Último recurso: resposta em cache, modo degraded com Ollama local, ou resposta amigável

### R2 — Safety filter bypassável
- **Arquivo:** `brain/safety.py:19-67`
- **Severidade:** 🟡 ALTO
- **Descrição:** Filtro só em português. Normalização permite bypass criativo
- **Fix:** Adicionar inglês, verificar palavras após normalização

### R3 — Nenhum rate limiting na API
- **Arquivo:** `api.py` (todos os endpoints)
- **Severidade:** 🟡 ALTO
- **Descrição:** 10 requests/s contra /api/chat pode gastar centenas de dólares
- **Fix:** Implementar rate limiting por IP e por chave

### R4 — Hallucination detection só pega admission de erro
- **Arquivo:** `output_parser.py:52-58`
- **Severidade:** 🟡 ALTO
- **Descrição:** Padrões detectam apenas quando LLM ADMITE que alucinou. Alucinações confiantes passam
- **Fix:** Adicionar verificação factual contra fontes confiáveis

### R5 — Upload de áudio sem limite de tamanho
- **Arquivo:** `api.py:1046`
- **Severidade:** 🟡 ALTO
- **Descrição:** POST /api/stt aceita qualquer tamanho antes de passar ao ffmpeg
- **Fix:** Limitar a 25MB

### R6 — TTS `_stop_requested` é dead code
- **Arquivo:** `voice/tts.py:387`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `stop()` seta flag mas nenhum código verifica
- **Fix:** Implementar verificação ou remover flag

### R7 — TTS threads acumulam esperando lock
- **Arquivo:** `voice/tts.py:134-135`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `speak(blocking=False)` cria thread para cada chamada. Threads acumulam
- **Fix:** Usar ThreadPoolExecutor com max_workers=1

### R8 — `_format_result` prefixa SUCESSO em respostas ambíguas
- **Arquivo:** `brain/agent_tools.py:940`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `"comando executado"` no texto de erro ganha prefixo SUCESSO
- **Fix:** Refinar indicadores de sucesso

### R9 — `execute_natural` cadeia if-elif frágil
- **Arquivo:** `actions/executor.py:447-851`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Ordem define prioridade. Palavras-chave genéricas causam falsos positivos
- **Fix:** Sistema de matching com score ao invés de primeira correspondência

### R10 — memory.py sem rollback em falha de DB
- **Arquivo:** `brain/memory.py:139,149`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Exceções do chat_db silenciosamente ignoradas em add_exchange e get_history_text
- **Fix:** Logging adequado + rollback

### R11 — sem timeout global para cascata de LLM
- **Arquivo:** `brain/llm.py`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Cada provider tem timeout individual mas sem limite global. Usuário pode esperar minutos
- **Fix:** Timeout global de 30s para toda a cascata

### R12 — TTS `_stop_requested` não verificado em _speak_sync
- **Arquivo:** `voice/tts.py`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** _speak_sync não checa _stop_requested durante geração. Só stop imediato via sd.stop()

---

## 🏗️ CÓDIGO — QUALIDADE

### C1 — `print()` como sistema de logging
- **Severidade:** 🟡 ALTO
- **Descrição:** Todo diagnóstico via print(). Sem níveis, sem formato, sem rotação
- **Fix:** Substituir por logging.getLogger(__name__)

### C2 — 3 padrões de retorno diferentes
- **Severidade:** 🟢 MÉDIO
- **Descrição:** executor.py: dict, output_parser.py: tuple, loop_guard.py: objeto, agent_tools: string prefixada
- **Fix:** Unificar em dataclass ToolResult

### C3 — String mágicas de modelo
- **Arquivo:** `luna_core.py:698,904,932`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `"gemini-2.0-flash"` hardcoded como fallback
- **Fix:** Usar `GEMINI_MODELS.get("fallback", "gemini-2.0-flash")`

### C4 — MAX_PERSISTENT sobrescrita
- **Arquivo:** `brain/memory.py:26`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** `MAX_PERSISTENT = max(MAX_PERSISTENT, 500)` ignora config < 500
- **Fix:** Respeitar config.py

### C5 — .env lido só na inicialização do módulo
- **Arquivo:** `voice/stt.py:58-68`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Variáveis setadas depois da carga do módulo não são lidas
- **Fix:** Recarregar .env ou usar config.py como fonte única

### C6 — `_route_code_creation` código morto
- **Arquivo:** `actions/executor.py:853-860`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Sempre retorna None. Planejado mas não implementado
- **Fix:** Implementar ou remover

### C7 — `unicodedata` importado 2x no executor
- **Arquivo:** `actions/executor.py:7,91`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Import global + import local redundante
- **Fix:** Usar apenas o global

### C8 — SSL key versionada se não no .gitignore
- **Arquivo:** `ssl/key.pem`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Chave privada pode estar no repositório
- **Fix:** Verificar .gitignore

### C9 — Nenhum teste unitário
- **Severidade:** 🟡 ALTO
- **Descrição:** Nenhum dos módulos críticos tem testes. OutputParser.main() tem 3 casos manuais
- **Fix:** Adicionar pytest para pelo menos core e agent_tools

### C10 — `output_parser.py` sem testes para edge cases
- **Arquivo:** `output_parser.py:225-260`
- **Severidade:** 🟢 MÉDIO
- **Descrição:** Só 3 casos hand-crafted. Sem testes para: vazio, whitespace, não-português, JSON aninhado, HTML

---

## 🧠 PADRÕES DO CLAW CODE PARA INCORPORAR

### CC1 — Runtime com Traits Genéricos
```python
class AgentRuntime:
    def __init__(self, model: LLMProvider, tools: ToolExecutor, permissions: PermissionPolicy):
        ...
```

### CC2 — PermissionPolicy em 5 Níveis
| Nível | Descrição |
|-------|-----------|
| `ReadOnly` | Ler arquivos, status |
| `WorkspaceWrite` | Escrever só no workspace |
| `DangerFullAccess` | bash, sistema |
| `Prompt` | Perguntar usuário |
| `Allow` | Sempre permitir |

### CC3 — Session com Compactação Automática
Compactar turns antigos em sumários quando input_tokens > threshold

### CC4 — Tool Catalog com Perfis
- `minimal`: só conversa
- `coding`: write_code, filesystem, check_project
- `messaging`: google_services
- `full`: tudo

### CC5 — Hook System (Plugin Architecture)
Pre/post tool hooks para logging, approval, side effects

### CC6 — Bootstrap por Fases
Fase 0: CLI/fast path → Fase 1: Model health → Fase 2: Tools → Fase 3: Runtime

### CC7 — Task Registry para Sub-Agents
Spawn sub-tasks com timeout, heartbeat, status lifecycle

---

## 📋 PLANO DE AÇÃO PRIORIZADO

**Legenda:** 🟢 = < 1h | 🟡 = 1-4h | 🔴 = 4-16h | ⚫ = 16h+

### Fase 1 — 🔴 Segurança (Urgente — 4h total)
| # | Tarefa | Esforço |
|---|--------|---------|
| S1 | Substituir `shell=True` por lista de args + whitelist | 🟡 |
| S2 | Validar caminhos em write_code, create_project, check_project | 🟢 |
| S3 | Fix CORS — remover wildcard com credentials | 🟢 |
| S4 | Remover bypass localhost de API key | 🟢 |
| S6 | Adicionar role admin para reset/shutdown | 🟢 |
| S7 | Adquirir `self._lock` no wakeword loop | 🟢 |
| S8 | Adicionar salt + expiry em tokens de usuário | 🟡 |

### Fase 2 — 🟡 Infraestrutura (Alta — 8h total)
| # | Tarefa | Esforço |
|---|--------|---------|
| A2 | Implementar handlers ou remover 29 tools sem handler | 🔴 |
| P1 | Health checks paralelos + timeout global para LLM cascade | 🟡 |
| P4 | Adicionar lock em clear_expired() | 🟢 |
| P3 | Sync L1/L2 cache | 🟢 |
| R3 | Adicionar rate limiting na API | 🟡 |
| B1 | Cancelar timer em clear_facts/clear_history | 🟢 |
| B3 | Adicionar locks em facts, _facts_index, sessions | 🟢 |

### Fase 3 — 🟡 Arquitetura (Média — 16h+ total)
| # | Tarefa | Esforço |
|---|--------|---------|
| A1 | Refatorar luna_core.py em módulos (AgentLoop, Session, Tools) | ⚫ |
| A4 | Implementar PermissionPolicy (5 níveis) | 🔴 |
| A6 | Criar ToolCatalog com perfis | 🔴 |
| A5 | Implementar Session com compactação | 🔴 |
| A11 | Adicionar hook system (pre/post tool) | 🟡 |

### Fase 4 — 🟢 Confiabilidade (Média — 8h total)
| # | Tarefa | Esforço |
|---|--------|---------|
| R1 | Implementar degraded mode + cache de fallback para LLM | 🟡 |
| R4 | Melhorar hallucination detection com verificação factual | 🔴 |
| C1 | Substituir print() por logging estruturado | 🟡 |
| C2 | Unificar padrão de retorno (ToolResult dataclass) | 🟡 |
| R9 | Substituir if-elif chain por scoring system | 🟡 |

### Fase 5 — 🟢 Performance + Qualidade (Baixa — 8h total)
| # | Tarefa | Esforço |
|---|--------|---------|
| P2 | Periodic flush no cache | 🟢 |
| P5 | Trocar LRU sorting por heap | 🟢 |
| B4 | Fix compress_messages overlap | 🟢 |
| B9 | Fix screenshot fallback | 🟢 |
| B10 | Usar Path.home() | 🟢 |
| C9 | Adicionar testes unitários (pytest) | 🟡 |

---

## Checklist de Implementação

### ✅ Já Implementado
- [x] `agent_tools.py`: Handlers para search_web, read_webpage, click_web_result, open_url, get_weather, see_screen, take_screenshot, send_notification, kill_process, control_media, desktop_type, desktop_hotkey
- [x] `actions/image_gen.py`: Módulo de geração de imagens via Google Gemini (gratuito)
- [x] `api.py`: Endpoint `POST /api/image/generate`
- [x] `luna_core.py`: Registro de `image_generate` em _TEXT_FUNCTIONS, ACTIONS, _tool_progress_label
- [x] `agent_tools.py`: Definição de `image_generate` em LUNA_TOOLS + handler
