### vou passar ajustando as funções antigas até que estejam lapidadas perfeitamente

- funções novas:
    **Luna Writing** você escreve sozinho (semelhante ao word) mas a luna dá sugestões de palavras ajusta e funciona em tempo real
    **Luna Math** Luna vai te ajudar na matematica como uma lousa digital te permitindo fazer o calculo e ter a ajuda dela
    **Luna BFF** com esse modo Luna vai receber buffs para hobbys apoio emocional, uma wiki para algo mais especifico
    **Luna Automation** em breve com o esp adicionarei automação em casas 
    **Luna eyes** além de poder enxergar o pc ela podera ver cameras de segurança para alertas de risco em casa 

#### Necessidade!
    **Placa de video** - O uso da cpu limita MUITO a efeiciencia e velocidade da ia, sem a GPU provavelmente em breve não poderei melhorar a agente  RTX 3060 12gb

## talvez precise
    **32gb de ram** - noto que em muitos momentos o pc chega a usar 70% para cima de ram sem falar que ddr3 não é mais tão eficiente
    **i7 de 4 geração** - é um processador muito bom mas está ficando velho e limitando a eficiência da ia

---

# 📋 Relatório de Funcionalidades — Luna (02/05/2026)

## Arquitetura Geral

O sistema Luna é uma assistente de IA local que roda no Arch Linux. O fluxo de processamento segue fases em cascata:

1. **Comandos internos** — status, apps, memória, ajuda, sair (sem IA)
2. **Escritor Engine** — detecta pedidos criativos e ativa pipeline de escrita com streaming
3. **Executor 1-Cauda** — roteamento por palavra-chave sem LLM (música, timer, notas, etc.)
4. **Dicionário local** — consultas de palavras sem LLM
5. **Cache inteligente** — respostas repetidas sem chamar o modelo
6. **LLM (Ollama)** — Qwen 2.5 em 4 tamanhos: 0.5B (fast), 3B (main), 7B (heavy), 0.5B (basic)

---

## 🎵 Música — Spotify

**Arquivo:** `actions/spotify.py`

Funciona em dois modos:

**Modo API** (requer `SPOTIPY_CLIENT_ID` e `SPOTIPY_CLIENT_SECRET` no `.env`):
- Busca músicas pela Web API do Spotify e toca diretamente
- Controla volume, próxima, anterior, pausar, retomar
- Detecta fim de faixa via API (`progress_ms` vs `duration_ms`)

**Modo Local** (padrão, sem credenciais):
- Abre o Spotify via `xdg-open spotify:search:QUERY` (handler do sistema)
- Controla via `playerctl --player=spotify`
- Detecta fim de faixa via `playerctl metadata mpris:length` e `playerctl position`

**Autoplay inteligente:** ao terminar uma música pedida diretamente, o modelo `fast` (0.5B) sugere uma música que combine com o mesmo ritmo/estilo. A Luna fala a sugestão e toca automaticamente. O autoplay se encadeia — cada sugestão dispara o próximo. Cancela automaticamente se o usuário pedir outra música.

**Comandos:** `toca [nome]`, `pausa`, `continua`, `próxima música`, `música anterior`, `volume [0-100]`, `que música está tocando`, `minha música favorita`, `músicas que gostei`, `minha playlist [nome]`

---

## 🎶 Playlist Inteligente

**Arquivo:** `actions/playlist_builder.py`

Gera e toca sequências de músicas usando o modelo `main` (3B):

1. Detecta intenção via regex rápido (`top N gênero`) ou LLM
2. Gera a lista completa via streaming (imprime em tempo real no terminal)
3. Para cada música: fala o nome via TTS, busca no Spotify e toca
4. Aguarda o fim da faixa via `playerctl` (posição + duração em microssegundos)
5. Avança para a próxima da sequência gerada pela IA

**Pular:** `pula` / `skip` → seta `_skip_flag`, o `_wait_for_track_end` retorna imediatamente e o loop busca a próxima da lista gerada.

**Parar:** `para a playlist` / `cancela playlist`

**Comandos:** `top 10 [gênero]`, `cria uma playlist de [N] músicas de [gênero]`, `monta [N] músicas de [gênero]`

---

## 📻 Rádio

**Arquivo:** `actions/media.py` — classe `RadioManager`

Toca streams de rádio via `mpv --no-video` (com fallback para `cvlc`). URLs testadas e funcionando:

| Rádio | Fonte |
|---|---|
| Metropolitana 98.5 | ice.fabricahost.com.br |
| Jovem Pan | brasilstream.com.br |
| Band FM | xcast.com.br |
| Mix FM | zeno.fm |
| Antena 1 | streamingcwsradio30.com |
| Transamérica | brasilstream.com.br |
| Cultura | zeno.fm |
| CBN | IP direto |
| Globo | IP direto |

Para rádios não listadas, busca automaticamente via `radio-browser.info` (API pública).

**Comandos:** `toca rádio [nome]`, `liga a rádio [nome]`, `para a rádio`

---

## ⏱ Timer

**Arquivo:** `actions/timer.py`

Cria timers com `threading.Timer`. Ao terminar: fala via TTS e envia notificação desktop (`notify-send`). Suporta múltiplos timers simultâneos com nomes diferentes.

**Comandos:** `timer de [N] minutos`, `alarme em [N] minutos para o [nome]`, `timers ativos`, `cancela o timer`

---

## 🔔 Lembretes

**Arquivo:** `actions/reminders.py`

Persiste lembretes em `data/reminders.json`. Thread de monitor verifica a cada 15 segundos. Ao disparar: notificação desktop + TTS. Suporta horários absolutos (`às 15h`), relativos (`em 2 horas`, `daqui 30 minutos`) e dias da semana.

**Comandos:** `me lembra de [algo] às [hora]`, `meus lembretes`, `cancela o lembrete [nome]`

---

## 📝 Notas

**Arquivo:** `actions/notes.py`

Persiste notas em `data/notes.json` com timestamp. Suporta adicionar, listar, deletar por índice, buscar por texto e limpar tudo.

**Comandos:** `anota: [texto]`, `minhas notas`, `apaga a nota [N]`, `busca nas notas [termo]`

---

## 🛒 Lista de Compras

**Arquivo:** `actions/shopping_list.py`

Persiste em `data/shopping_list.json`. Detecta duplicatas. Parser via regex para extrair o item do comando.

**Comandos:** `adiciona [item] na lista`, `ver lista`, `já comprei [item]`, `limpa a lista`

---

## 🌤 Clima

**Arquivo:** `actions/weather.py`

Consulta `wttr.in` (sem chave de API). Cache de 30 minutos por cidade. Retorna temperatura atual, sensação térmica, mín/máx do dia, umidade, vento e chance de chuva se > 30%.

**Comandos:** `como está o tempo`, `clima em [cidade]`, `vai chover hoje`, `temperatura em [cidade]`

---

## 🎯 Foco / Pomodoro

**Arquivo:** `actions/focus.py`

Sessões de foco com `threading.Event` (cancelável imediatamente). Ao terminar: TTS + notificação. Salva histórico em `data/focus_log.json`.

**Comandos:** `modo foco por [N] minutos`, `pomodoro`, `cancela o foco`, `status do foco`, `estatísticas de foco`

---

## 🪟 Janelas

**Arquivo:** `actions/window_manager.py`

Controla janelas via `hyprctl dispatch` (Hyprland) com fallback para `xdotool`. Suporta fechar, minimizar, maximizar, tela cheia, modo flutuante, trocar de workspace e mover janelas.

**Comandos:** `fecha essa janela`, `minimiza`, `maximiza`, `tela cheia`, `workspace [N]`, `janela para esquerda/direita`

---

## 📋 Clipboard

**Arquivo:** `actions/clipboard.py`

Lê e escreve na área de transferência. Detecta automaticamente `wl-paste`/`wl-copy` (Wayland) ou `xclip`/`xsel` (X11).

**Comandos:** `o que tem no clipboard`, `copia [texto]`

---

## 🎤 Voz (TTS/STT)

**Arquivo:** `voice/tts.py`, `voice/voice_engine.py`, `voice/stt.py`

- **TTS:** Kokoro ONNX local (pt-BR) com fallback para Edge TTS online. Suporta entonação emocional (feliz, triste, animado, calmo, surpreso).
- **STT:** Whisper local para reconhecimento de fala.
- **Wake word:** `"ei luna"`, `"luna"`, `"hey luna"`

---

## 👁 Visão de Tela

**Arquivo:** `vision/screen.py`

Captura e descreve a tela via OCR. Verifica resultado de ações de UI (janela mudou, app abriu).

**Comandos:** `o que você está vendo`, `ver a tela`, `descreva a tela`

---

## 🌐 Web / Apps

- **Pesquisa:** abre Firefox com a query
- **Apps:** abre qualquer app listado em `apps.json` via comando configurado
- **Screenshot:** `scrot` ou `gnome-screenshot`

---

## 💻 Código / Escrita

- **Código:** modelo `heavy` (7B) gera e salva arquivos
- **Escritor Engine:** pipeline criativo com streaming para textos longos, histórias, poemas

---

## ⚙ Configuração

**Arquivo:** `config.py`

Carrega `.env` automaticamente na inicialização. Variáveis principais:
- `SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET` — opcional, ativa modo API do Spotify
- `OLLAMA_URL` — URL do servidor Ollama (padrão: `localhost:11434`)
- `LUNA_MODEL_*` — sobrescreve os modelos padrão
- `LUNA_TTS_VOICE` — voz do Edge TTS
