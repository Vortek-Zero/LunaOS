#!/usr/bin/env python3
"""
luna_terminal.py — Terminal de Referência da Luna
Exibe todas as palavras-chave e comandos disponíveis em um painel colorido.

Uso:
    python luna_terminal.py           # mostra a tabela completa
    python luna_terminal.py --watch   # atualiza em loop (CTRL+C para sair)
"""

import sys
import os
import time
import shutil

# ── Cores ANSI ────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# Foreground
CYAN   = "\033[96m"
BLUE   = "\033[94m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
MAGENTA= "\033[95m"
WHITE  = "\033[97m"
GRAY   = "\033[90m"

# Background
BG_BLACK = "\033[40m"
BG_DARK  = "\033[48;5;234m"

def clr(text, *codes):
    return "".join(codes) + str(text) + RESET

def title_block(text: str, color=CYAN) -> str:
    term_w = shutil.get_terminal_size((80, 24)).columns
    pad = max(0, (term_w - len(text) - 4) // 2)
    line = "─" * (term_w - 2)
    return (
        f"\n{clr('┌' + line + '┐', color)}\n"
        f"{clr('│', color)}{' ' * pad}{clr(BOLD + text + RESET, WHITE)}{' ' * pad}{' ' * ((term_w - len(text) - 4) % 2)}{clr('│', color)}\n"
        f"{clr('└' + line + '┘', color)}\n"
    )

def section(label: str, color=BLUE) -> str:
    return f"\n  {clr('▸', color)} {clr(BOLD + label.upper() + RESET, WHITE)}\n"

def kw_row(keyword: str, desc: str, w_kw=32) -> str:
    kw_fmt = clr(f"  {keyword:<{w_kw}}", CYAN)
    desc_fmt = clr(desc, GRAY)
    return f"{kw_fmt}{desc_fmt}"

def divider(color=GRAY, char="─") -> str:
    term_w = shutil.get_terminal_size((80, 24)).columns
    return clr("  " + char * (term_w - 4), color)


# ── Dados de referência ───────────────────────────────────────

KEYWORDS = {
    "🔧 Comandos Internos": [
        ("status",                      "Exibe status completo do sistema (LLM, mic, cache)"),
        ("apps",                        "Lista todos os apps disponíveis para abrir"),
        ("memoria",                     "Mostra quantas memórias/histórico a Luna tem"),
        ("limpar  /  limpa memoria",    "Apaga o histórico da conversa"),
        ("funções  /  ajuda",           "Mostra um resumo do que a Luna pode fazer"),
        ("performance",                 "Tempo médio de resposta e hits de cache"),
        ("sair  /  exit  /  tchau",     "Encerra a Luna"),
    ],
    "💬 Modos de Conversa": [
        ("vamos conversar",             "Ativa o Modo Conversa (IA mais livre, bate-papo)"),
        ("até mais",                    "Desativa o Modo Conversa e volta ao fluxo padrão"),
        ("conversar",                   "Alias para ativar o modo conversa"),
    ],
    "⏱ Timer & Tempo": [
        ("timer de X minutos",          "Cria um timer de contagem regressiva"),
        ("alarme em X minutos",         "Alias para timer"),
        ("cronômetro de X segundos",    "Timer em segundos"),
        ("me avisa em X minutos",       "Timer com phrasing natural"),
        ("daqui a X horas",             "Timer com horas"),
        ("timers  /  timers ativos",    "Lista timers em execução"),
    ],
    "🛒 Lista de Compras": [
        ("adiciona X na lista",         "Adiciona item à lista de compras"),
        ("adicione X na lista de compras", "Alias mais formal"),
        ("ver lista  /  lista de compras", "Exibe a lista atual"),
        ("já comprei X",                "Remove item da lista"),
        ("limpa a lista",               "Esvazia a lista de compras"),
        ("remove X da lista",           "Remove item específico"),
        ("lista",                       "Atalho interno para ver a lista"),
    ],
    "🔔 Lembretes": [
        ("me lembra de X às HH:MM",    "Cria lembrete com horário"),
        ("me lembre de X",              "Lembrete mais simples"),
        ("lembra de X",                 "Alias natural"),
        ("meus lembretes  /  lembretes","Lista todos os lembretes ativos"),
        ("criar lembrete X",            "Alias formal"),
    ],
    "📝 Notas": [
        ("anota: X",                    "Salva uma nota rápida"),
        ("anote X",                     "Alias para anotar"),
        ("minhas notas  /  notas",      "Lista todas as notas"),
        ("ver notas",                   "Exibe as notas salvas"),
        ("apaga a nota X",              "Remove nota por número/conteúdo"),
    ],
    "🎵 Música (Spotify)": [
        ("toca música",                 "Retoma a reprodução atual (abre o app se necessário)"),
        ("toca [nome da música]",       "🔍 Busca e toca a música EXATA — dispara autoplay ao terminar"),
        ("toca [nome do artista]",      "Busca artista → toca a top track dele automaticamente"),
        ("minha música favorita",       "Toca o atalho favorito (Montagem xonada)"),
        ("minha playlist [nome]",       "Abre a playlist definida no arquivo playlists.json"),
        ("quero ouvir [nome]",          "Alias para busca de música/artista"),
        ("músicas que gostei",          "Abre a coleção de Músicas Curtidas do Spotify"),
        ("próxima música",              "Avança para a próxima faixa"),
        ("música anterior",             "Volta para a faixa anterior"),
        ("para a música  /  pausa",     "Pausa a reprodução"),
        ("continua  /  retoma",         "Retoma a reprodução pausada"),
        ("aumenta o volume",            "Aumenta volume do player"),
        ("diminui o volume",            "Diminui volume do player"),
        ("volume [0-100]",              "Volume específico (ex: volume 70, volume para 80)"),
        ("que música está tocando",     "Informa artista e título da música atual"),
        ("— Autoplay inteligente —",    "Ao terminar a música, IA sugere e toca uma que combine"),
    ],
    "📻 Rádio": [
        ("toca rádio [nome]",           "Abre stream de rádio via mpv (sem navegador)"),
        ("coloca a rádio [nome]",       "Alias para tocar rádio"),
        ("liga a rádio [nome]",         "Alias para tocar rádio"),
        ("para a rádio",                "Para o stream de rádio em andamento"),
        ("— Rádios disponíveis —",      "metropolitana, jovem pan, band, mix, antena 1, transamérica, cultura, cbn, globo"),
    ],
    "🎶 Playlist Inteligente (IA)": [
        ("top 10 [gênero]",                         "Gera e toca as 10 mais tocadas do gênero"),
        ("toca top 20 melhores eletrônicas",         "Exemplo: top N + gênero"),
        ("cria uma playlist [gênero] de N músicas",  "Playlist com quantidade definida"),
        ("cria uma playlist para estudar calma pop", "Pedido expressivo — IA interpreta o contexto"),
        ("monta 30 músicas de jazz relaxante",       "Alias expressivo para criar playlist"),
        ("pula  /  próxima  /  skip",                "⏭ Pula e busca a próxima da sequência gerada pela IA"),
        ("para a playlist  /  cancela playlist",     "⏹ Interrompe a playlist em andamento"),
        ("— Anúncio por voz —",                      "Luna fala 'Top 1: Shape of You' antes de cada música"),
    ],
    "🌤 Clima": [
        ("como está o tempo",           "Previsão do tempo atual"),
        ("vai chover hoje",             "Verifica probabilidade de chuva"),
        ("clima em [cidade]",           "Clima de uma cidade específica"),
        ("temperatura em [cidade]",     "Temperatura atual de uma cidade"),
        ("previsão para amanhã",        "Previsão do tempo para amanhã"),
    ],
    "🪟 Janelas": [
        ("fecha essa janela",           "Fecha a janela ativa"),
        ("minimiza",                    "Minimiza a janela ativa"),
        ("maximiza",                    "Maximiza a janela ativa"),
        ("tela cheia  /  fullscreen",   "Coloca a janela em tela cheia"),
        ("workspace [N]",               "Vai para o workspace/área de trabalho N"),
        ("janela para esquerda/direita","Snap da janela para metade da tela"),
    ],
    "📋 Área de Transferência": [
        ("o que tem no clipboard",      "Lê o conteúdo copiado"),
        ("área de transferência",       "Alias para clipboard"),
        ("clipboard",                   "Mostra o que está na área de transferência"),
    ],
    "🎯 Foco / Pomodoro": [
        ("modo foco por X minutos",     "Inicia sessão de foco cronometrada"),
        ("pomodoro",                    "Inicia pomodoro de 25 minutos (padrão)"),
        ("sessão de foco",              "Alias para modo foco"),
        ("cancela o foco",              "Cancela a sessão ativa"),
        ("foco  /  status do foco",     "Verifica status da sessão atual"),
    ],
    "🔄 Atualizações": [
        ("versao  /  versão",           "Mostra a versão atual do Luna"),
        ("atualizar  /  update",        "Verifica se há nova versão no GitHub"),
        ("testar atualização",          "Simula notificação de atualização"),
    ],
    "🖥 Controle do Sistema": [
        ("abra [app]  /  abrir [app]", "Abre qualquer aplicativo instalado"),
        ("role para cima/baixo",        "Rola a tela atual"),
        ("clique em [elemento]",        "Clica em elemento de texto na tela"),
        ("clica em [elemento]",         "Alias de clique"),
        ("digite [texto]",              "Digita texto na aplicação ativa"),
        ("dá enter",                    "Pressiona a tecla Enter"),
        ("aperta esc",                  "Pressiona Escape"),
        ("aperta tab",                  "Pressiona Tab"),
        ("screenshot  /  tira print",   "Captura a tela atual"),
    ],
    "🌐 Web": [
        ("pesquise sobre [tema]",       "Abre navegador pesquisando o tema"),
        ("busque [tema]",               "Alias para pesquisar"),
        ("abra o [site].com",           "Abre URL diretamente no Firefox"),
        ("open_url [url]",              "Abre URL completa via ação LLM"),
    ],
    "✍ Criação de Conteúdo": [
        ("escreva uma história sobre X","Ativa o Escritor Engine (streaming)"),
        ("crie um texto sobre X",       "Alias para modo escritor"),
        ("redija um artigo sobre X",    "Escritor com estilo formal"),
        ("faça um poema sobre X",       "Escritor modo poesia"),
        ("modelo médio/alto",           "Troca o modelo do escritor (3B ou 7B)"),
    ],
    "💻 Código": [
        ("faça um script python que X", "Gera código via stream e salva em arquivo"),
        ("programe X em [linguagem]",   "Alias para geração de código"),
        ("crie um arquivo X.py com X",  "Gera código e salva com nome específico"),
        ("desenvolva X",                "Alias mais formal"),
    ],
    "🔍 Dicionário": [
        ("o que significa [palavra]",   "Consulta o dicionário interno"),
        ("definição de [palavra]",      "Alias para consulta"),
        ("como se usa [palavra]",       "Uso e exemplos da palavra"),
        ("sinônimos de [palavra]",      "Lista sinônimos"),
    ],
    "👁 Visão de Tela": [
        ("o que você está vendo",       "Captura e descreve a tela atual via OCR"),
        ("ver a tela",                  "Alias para captura de tela"),
        ("o que está aberto",           "Mostra janelas abertas (via xdotool)"),
        ("descreva a tela",             "OCR completo do que está na tela"),
    ],
}

MODEL_TABLE = {
    "1 Cauda (Bypass)":   ("Comandos diretos sem IA — timer, lista, notas, música, rádio...", GREEN),
    "2 Caudas (Fast)":    ("Ações rápidas de UI — clique, digitar, scroll, pesquisar",        BLUE),
    "3 Caudas (Main 3B)": ("Chat inteligente padrão — perguntas, bate-papo, cálculos",        CYAN),
    "4 Caudas (Heavy 7B)":("Código, análise profunda, escrita longa",                         MAGENTA),
    "Escritor Engine":    ("Pipeline criativo: planejar → rascunho stream → refinamento",     YELLOW),
    "Playlist IA":        ("Detecção expressiva (3B) → stream da lista → busca sequencial",   GREEN),
    "Autoplay (Fast 0.5B)":("Ao fim da música, sugere próxima que combine e toca automaticamente", CYAN),
    "Cache":              ("Resposta instantânea (zero LLM) para perguntas repetidas",        GREEN),
}


def render():
    os.system("clear" if os.name == "posix" else "cls")

    print(title_block("LUNA — GUIA DE PALAVRAS-CHAVE E COMANDOS", CYAN))

    for category, items in KEYWORDS.items():
        print(section(category, CYAN))
        for kw, desc in items:
            print(kw_row(kw, desc))
        print()

    print(divider(CYAN, "═"))
    print(section("🧠 Modelos de IA — Arquitetura Kitsuune", MAGENTA))
    for model, (desc, color) in MODEL_TABLE.items():
        print(kw_row(clr(model, color + BOLD), desc, w_kw=32))

    print(divider(CYAN, "═"))

    print(f"\n  {clr(BOLD + 'ENTONAÇÃO DE VOZ', WHITE)}")
    print(kw_row("Feliz (happy)",    "Rate +18% | Pitch +4Hz — resposta animada"))
    print(kw_row("Triste (sad)",     "Rate -12% | Pitch -3Hz — resposta lenta e suave"))
    print(kw_row("Surpreso",         "Rate +8%  | Pitch +5Hz — reação a algo inesperado"))
    print(kw_row("Calmo",            "Rate -5%  | Pitch -1Hz — modo sereno e tranquilo"))
    print(kw_row("Animado (excited)","Rate +22% | Pitch +6Hz — novo, descoberta, conquista"))
    print(kw_row("Neutro",           "Rate +5%  | Pitch +2Hz — padrão de conversa"))

    print(divider(GRAY))
    print(f"\n  {clr(DIM, GRAY)}Dica: use 'python luna_terminal.py --watch' para manter o painel ativo{RESET}\n")


def main():
    watch = "--watch" in sys.argv

    if watch:
        print(clr("Modo watch ativado (CTRL+C para sair)...", YELLOW))
        time.sleep(1)
        try:
            while True:
                render()
                time.sleep(30)
        except KeyboardInterrupt:
            print(clr("\n\nTerminal encerrado.", CYAN))
    else:
        render()


if __name__ == "__main__":
    main()
