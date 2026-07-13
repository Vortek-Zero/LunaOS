# Sistema de Personalidade — Luna

## Visão Geral

A personalidade da Luna é definida em duas camadas:

1. **`config/personality.json`** — arquivo de configuração editável (sem mexer em código)
2. **`luna_core.py`** — carrega o JSON e injeta as regras no system prompt do LLM

## Arquivos Envolvidos

| Arquivo | Função |
|---------|--------|
| `config/personality.json` | Todas as regras de personalidade, tom, estilo de resposta |
| `luna_core.py` (`_load_persona`) | Carrega o JSON e guarda em `self._personality_data` |
| `luna_core.py` (`_run_autonomous_loop`) | Injeta as regras de `response_style` no system prompt |

## Estrutura do `personality.json`

### `identity`
Dados básicos: nome, versão, criador, idioma.

### `personality`
Descrição geral e traços de personalidade (sincera, empática, madura, direta, proativa, inteligente).

### `voice`
Configuração de voz (TTS): voice_id, tom, velocidade.

### `emotional_rules`
Regras de tom emocional:
- `serious_mode` — disparado por palavras como "morte", "tristeza", "hospital"
- `light_mode` — disparado por "parabéns", "consegui", "aprovei"
- `normal_mode` — tom padrão do dia a dia

### `safety_rules`
Tópicos proibidos e respostas de recusa.

### `behavioral_rules`
Regras de comportamento: honestidade, não alucinar, fala natural, etc.

### `response_style` *(adicionado em 12/07/2026)*
Estilo de resposta Jarvis + Grok:

| Campo | Descrição |
|-------|-----------|
| `essence` | Objetivo principal e personalidade base |
| `principles` | 4 princípios fundamentais (brevidade, tom natural, estrutura visual, utilidade) |
| `flow` | Ordem da resposta: direta → explicação → visual → fechamento |
| `language` | Tom, max linhas por parágrafo, vocabulário, ritmo |
| `rules.always` | O que SEMPRE fazer (negrito, blocos, proatividade) |
| `rules.never` | O que NUNCA fazer (textão, respostas vagas, formalidade) |

## Como o sistema prompt é montado

Em `luna_core.py:_run_autonomous_loop`:

1. System prompt base (princípios de engenharia, regras absolutas, ferramentas)
2. **Regras de `response_style` injetadas dinamicamente** — lê do `personality.json` via `self._personality_data`
3. Bloco específico do modo (code, voice, write, joy)

## Como Editar

Para mudar o estilo de resposta da Luna, edite **apenas** o `config/personality.json`:

- Para mudar tom: altere `response_style.language.tone`
- Para mudar o fluxo: altere `response_style.flow`
- Para adicionar/remover regras: altere `response_style.rules`

Não é necessário modificar `luna_core.py` a menos que queira mudar a estrutura de como as regras são injetadas.

## Exemplo de Resposta (pós-alteração)

**Usuário:** "Liga a luz da sala"
**Luna:** Feito. Luz da sala acesa.
Quer que eu ajuste a intensidade ou ligue mais alguma coisa?
