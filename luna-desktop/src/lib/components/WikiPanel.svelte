<script lang="ts">
  import Icon from './Icon.svelte';

  let { onSelectCommand } = $props<{
    onSelectCommand: (cmd: string) => void;
  }>();

  let filterText = $state('');

  const WIKI = [
    { cat: '⏱ Timer & Alarme', cmds: [
      { ex: 'timer de 10 minutos', desc: 'Inicia contagem regressiva de 10 min' },
      { ex: 'alarme em 30 segundos', desc: 'Alarme em 30 segundos' },
      { ex: 'me avisa em 1 hora', desc: 'Aviso após 1 hora' },
      { ex: 'timers ativos', desc: 'Lista timers em andamento' },
    ]},
    { cat: '🛒 Lista de Compras', cmds: [
      { ex: 'adiciona leite na lista', desc: 'Adiciona item à lista' },
      { ex: 'adicione pão e ovos', desc: 'Adiciona múltiplos itens' },
      { ex: 'ver lista', desc: 'Lê a lista de compras' },
      { ex: 'já comprei leite', desc: 'Remove item da lista' },
      { ex: 'limpa a lista', desc: 'Apaga toda a lista' },
    ]},
    { cat: '📝 Notas', cmds: [
      { ex: 'anota: reunião às 15h', desc: 'Salva uma nota rápida' },
      { ex: 'anote que preciso ligar', desc: 'Salva nota com texto livre' },
      { ex: 'minhas notas', desc: 'Lista todas as notas' },
      { ex: 'apaga a nota 2', desc: 'Remove nota pelo número' },
    ]},
    { cat: '🔔 Lembretes', cmds: [
      { ex: 'me lembra de tomar remédio às 20h', desc: 'Lembrete com horário' },
      { ex: 'me lembre de ligar amanhã às 9h', desc: 'Lembrete para amanhã' },
      { ex: 'meus lembretes', desc: 'Lista lembretes ativos' },
    ]},
    { cat: '🎵 Música & Mídia', cmds: [
      { ex: 'toca música', desc: 'Retoma reprodução' },
      { ex: 'pausa', desc: 'Pausa a música' },
      { ex: 'próxima música', desc: 'Avança para a próxima faixa' },
      { ex: 'música anterior', desc: 'Volta para a faixa anterior' },
      { ex: 'aumenta o volume', desc: 'Sobe o volume' },
      { ex: 'diminui o volume', desc: 'Baixa o volume' },
      { ex: 'o que está tocando?', desc: 'Mostra a música atual' },
      { ex: 'toca rádio CBN', desc: 'Toca rádio pelo nome' },
      { ex: 'para o rádio', desc: 'Para o rádio' },
      { ex: 'monta uma playlist de jazz', desc: 'Cria playlist por gênero com IA' },
      { ex: 'para a playlist', desc: 'Encerra a playlist' },
    ]},
    { cat: '🌤 Clima', cmds: [
      { ex: 'como está o tempo?', desc: 'Clima na cidade padrão' },
      { ex: 'vai chover hoje?', desc: 'Previsão de chuva' },
      { ex: 'tempo em São Paulo', desc: 'Clima em cidade específica' },
    ]},
    { cat: '💡 Luzes', cmds: [
      { ex: 'liga a luz da sala', desc: 'Acende a luz' },
      { ex: 'apaga a luz da sala', desc: 'Apaga a luz' },
      { ex: 'apagar a luz às 21h', desc: 'Agenda apagar às 21:00 todos os dias' },
      { ex: 'ligar a luz às 7:30', desc: 'Agenda ligar às 07:30 todos os dias' },
      { ex: 'apagar a luz às 22h de segunda a sexta', desc: 'Agenda só nos dias de semana' },
      { ex: 'agendamentos', desc: 'Lista todos os agendamentos de luz' },
    ]},
    { cat: '🎉 Modo Balada / Luzes', cmds: [
      { ex: 'modo balada', desc: 'Ativa pisca-pisca colorido' },
      { ex: 'modo festa', desc: 'Igual ao modo balada' },
      { ex: 'para a balada', desc: 'Desativa efeitos de luz' },
      { ex: 'SOS', desc: 'Sinal de emergência piscante' },
      { ex: 'metrônomo 120 bpm', desc: 'Pisca no ritmo do BPM' },
      { ex: 'morse olá', desc: 'Transmite texto em código Morse' },
    ]},
    { cat: '🪟 Janelas & Workspace', cmds: [
      { ex: 'fecha essa janela', desc: 'Fecha a janela ativa' },
      { ex: 'maximiza', desc: 'Maximiza a janela ativa' },
      { ex: 'minimiza', desc: 'Minimiza a janela ativa' },
      { ex: 'workspace 2', desc: 'Vai para o workspace 2' },
      { ex: 'move para workspace 3', desc: 'Move janela para workspace 3' },
      { ex: 'tela cheia', desc: 'Ativa modo tela cheia' },
      { ex: 'divide à esquerda', desc: 'Encaixa janela à esquerda' },
      { ex: 'divide à direita', desc: 'Encaixa janela à direita' },
    ]},
    { cat: '📋 Clipboard', cmds: [
      { ex: 'o que está na área de transferência?', desc: 'Lê o conteúdo copiado' },
      { ex: 'copia isso para o clipboard', desc: 'Copia texto para clipboard' },
    ]},
    { cat: '🎯 Foco / Pomodoro', cmds: [
      { ex: 'modo foco por 25 minutos', desc: 'Inicia sessão Pomodoro' },
      { ex: 'pausa de 5 minutos', desc: 'Pausa do Pomodoro' },
      { ex: 'cancela o foco', desc: 'Encerra sessão de foco' },
      { ex: 'status do foco', desc: 'Mostra tempo restante' },
    ]},
    { cat: '✍️ Escrita Criativa', cmds: [
      { ex: 'escreva uma história sobre dragões', desc: 'Gera história com IA' },
      { ex: 'crie um poema sobre o mar', desc: 'Gera poema' },
      { ex: 'redija um e-mail formal', desc: 'Escreve e-mail' },
      { ex: 'crie um artigo sobre tecnologia', desc: 'Gera artigo' },
    ]},
    { cat: '💻 Código', cmds: [
      { ex: 'crie um script python que lê CSV', desc: 'Gera código Python' },
      { ex: 'escreva uma função em JavaScript', desc: 'Gera código JS' },
      { ex: 'crie um arquivo chamado app.py', desc: 'Cria arquivo de código' },
    ]},
    { cat: '🔍 Dicionário', cmds: [
      { ex: 'o que significa efêmero?', desc: 'Define a palavra' },
      { ex: 'definição de resiliência', desc: 'Busca definição' },
    ]},
    { cat: '🌐 Web & Apps', cmds: [
      { ex: 'pesquise sobre Python', desc: 'Busca no navegador' },
      { ex: 'abra o youtube.com', desc: 'Abre URL no navegador' },
      { ex: 'abre o Spotify', desc: 'Abre aplicativo' },
      { ex: 'apps', desc: 'Lista apps disponíveis' },
    ]},
    { cat: '🖥 Tela & Visão', cmds: [
      { ex: 'o que você está vendo?', desc: 'Descreve a tela atual' },
      { ex: 'tira um print', desc: 'Captura a tela' },
      { ex: 'clica em Salvar', desc: 'Clica em elemento na tela' },
    ]},
    { cat: '💬 Conversa & Sistema', cmds: [
      { ex: 'o que temos pra hoje', desc: '☀️ Briefing diário: clima, lembretes, notas e frase do dia' },
      { ex: 'briefing do dia', desc: 'Igual ao anterior — resumo completo do dia' },
      { ex: 'vamos conversar', desc: 'Ativa modo conversa livre' },
      { ex: 'até mais', desc: 'Sai do modo conversa' },
      { ex: 'status', desc: 'Estado do sistema' },
      { ex: 'memória', desc: 'Estatísticas de memória' },
      { ex: 'limpa memória', desc: 'Apaga histórico da sessão' },
      { ex: 'o que você pode fazer?', desc: 'Lista de capacidades' },
      { ex: 'performance', desc: 'Métricas de desempenho' },
    ]},
  ];

  let filteredWiki = $derived.by(() => {
    const f = filterText.toLowerCase().trim();
    if (!f) return WIKI;
    return WIKI.map(sec => ({
      ...sec,
      cmds: sec.cmds.filter(c => c.ex.toLowerCase().includes(f) || c.desc.toLowerCase().includes(f))
    })).filter(sec => sec.cmds.length > 0);
  });
</script>

<div class="panel-view">
  <div class="panel-header">
    <Icon name="book-open" />
    <h2>Wiki de Comandos</h2>
  </div>
  <div class="panel-body">
    <div class="search-bar-row">
      <input
        class="field"
        type="text"
        bind:value={filterText}
        placeholder="Buscar comando por palavra-chave..."
      />
      <Icon name="search" size="16" class="search-icon" />
    </div>

    <div class="wiki-content">
      {#each filteredWiki as section}
        <div class="section-title">{section.cat}</div>
        <div class="card font-sans">
          {#each section.cmds as cmd}
            <button class="list-item" onclick={() => onSelectCommand(cmd.ex)} title="Clique para enviar ao chat">
              <div class="cmd-info">
                <span class="cmd-ex">{cmd.ex}</span>
                <span class="cmd-desc">{cmd.desc}</span>
              </div>
              <span class="arrow">▶</span>
            </button>
          {/each}
        </div>
      {:else}
        <div class="no-data">Nenhum comando encontrado para "{filterText}".</div>
      {/each}
    </div>
  </div>
</div>

<style>
  .panel-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; animation: fadeInUp 0.4s ease both; }
  .panel-header { display: flex; align-items: center; gap: 10px; padding: 16px 32px; flex-shrink: 0; }
  .panel-header h2 { font-size: 18px; font-weight: 600; color: rgba(255, 255, 255, 0.8); }
  .panel-header :global(svg) { color: var(--accent-blue); }
  
  .panel-body { flex: 1; overflow-y: auto; padding: 0 32px 32px; display: flex; flex-direction: column; gap: 16px; max-width: 680px; }

  .search-bar-row { position: relative; width: 100%; display: flex; align-items: center; }
  .field { width: 100%; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; color: white; font-size: 13.5px; padding: 12px 14px 12px 42px; outline: none; }
  .field:focus { border-color: rgba(59,158,255,0.3); background: rgba(255,255,255,0.02); }
  .search-bar-row :global(.search-icon) { position: absolute; left: 16px; color: rgba(255,255,255,0.25); }

  .wiki-content { display: flex; flex-direction: column; gap: 14px; }

  .section-title { font-size: 11px; font-weight: 700; color: rgba(255, 255, 255, 0.35); letter-spacing: 0.12em; text-transform: uppercase; margin-top: 10px; margin-bottom: 2px; }

  .card { background: rgba(15, 15, 30, 0.5); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 16px; padding: 6px 0; display: flex; flex-direction: column; position: relative; overflow: hidden; }
  .card:hover { border-color: rgba(59, 158, 255, 0.15); transition: all 0.25s ease; }

  .list-item { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; text-align: left; background: transparent; border: none; padding: 10px 18px; border-bottom: 1px solid rgba(255,255,255,0.03); cursor: pointer; transition: all 0.2s; }
  .list-item:last-child { border-bottom: none; }
  .list-item:hover { background: rgba(255,255,255,0.03); }
  .list-item:hover .arrow { color: #3b9eff; transform: translateX(2px); }

  .cmd-info { display: flex; flex-direction: column; gap: 2px; flex: 1; }
  .cmd-ex { font-size: 13px; font-weight: 600; color: #a78bfa; font-family: 'Inter', sans-serif; }
  .cmd-desc { font-size: 11px; color: rgba(255,255,255,0.45); }
  .arrow { font-size: 10px; color: rgba(255,255,255,0.25); transition: all 0.2s; }

  .no-data { font-size: 13px; color: rgba(255,255,255,0.3); text-align: center; padding: 24px; }
</style>
