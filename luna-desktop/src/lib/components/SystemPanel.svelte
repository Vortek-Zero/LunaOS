<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();

  let metrics = $state({ cpu_percent: 0, ram_percent: 0, disk_percent: 0, ram_used_gb: 0, ram_total_gb: 0 });
  let apps = $state<string[]>([]);
  let openAppName = $state('');
  let facts = $state<Array<{ fact: string; category?: string }>>([]);
  let factsHeader = $state('0 fatos');
  let perfInfo = $state({ avg_request_ms: 0, cache_hits: 0, cache_misses: 0, total_entries: 0 });
  let providers = $state<Array<{ name: string; active: boolean; available: boolean; rate_limited_for: number; model?: string; models?: Record<string, { name: string; rate_limited_for: number }> }>>([]);
  let upd = $state({ current: '', latest: '', commits_ahead: 0, update_available: false, commits: [] as string[], checking: false, applying: false, result: '' });

  // Settings state
  let cascadeOrder = $state('');
  let cascadeMsg = $state('');
  let crewEnabled = $state(false);
  let crewMsg = $state('');
  let writingModel = $state('medium');
  let modelMsg = $state('');
  let ttsProviders = $state<string[]>([]);
  let ttsCurrent = $state('edge_tts');
  let ttsVoices = $state<Record<string, string[]>>({});
  let ttsVoice = $state('');
  let ttsMsg = $state('');

  async function loadMetrics() {
    const res = await luna.fetchSystemMetrics();
    if (res && !res.error) {
      metrics = res;
    }
  }

  async function loadApps() {
    const res = await luna.fetchSystemApps();
    if (res && res.apps) {
      apps = res.apps;
    }
  }

  async function openApp(name: string) {
    if (!name) return;
    await luna.openSystemApp(name);
    openAppName = '';
  }

  async function loadFacts() {
    const res = await luna.fetchSystemFacts();
    if (res && res.facts) {
      facts = res.facts;
      const sizeKb = (JSON.stringify(res.facts).length / 1024).toFixed(1);
      factsHeader = `${res.facts.length} fatos · ${sizeKb} KB`;
    }
  }

  async function clearFacts() {
    if (!confirm('Limpar todos os fatos da memória persistente?')) return;
    await luna.deleteSystemFacts();
    await loadFacts();
  }

  async function resetAll() {
    if (!confirm('ATENÇÃO: Limpar TODO o sistema (chat, memória, notas, lista)? Isso não pode ser desfeito.')) return;
    await luna.resetSystem();
    alert('Sistema resetado! Reinicie o backend para aplicar as mudanças.');
    window.location.reload();
  }

  async function loadPerf() {
    const p = await luna.fetchPerformance();
    if (p) {
      perfInfo = {
        avg_request_ms: p.avg_request_ms || 0,
        cache_hits: p.cache_hits || 0,
        cache_misses: p.cache_misses || 0,
        total_entries: p.cache_entries || 0,
      };
    }
  }

  async function loadModels() {
    const res = await luna.fetchModelsStatus();
    if (res && res.providers) {
      providers = res.providers;
      if (res.cascade) cascadeOrder = Array.isArray(res.cascade) ? res.cascade.join(',') : res.cascade;
    }
  }

  async function loadTts() {
    const res = await luna.fetchTtsProviders();
    if (res) {
      ttsProviders = res.providers || [];
      ttsCurrent = res.current || 'edge_tts';
      ttsVoices = res.voices || {};
      ttsVoice = res.voice || '';
    }
  }

  async function saveCascade() {
    cascadeMsg = 'Salvando...';
    const res = await luna.setCascade(cascadeOrder);
    cascadeMsg = res?.message || 'Erro ao salvar';
    setTimeout(() => cascadeMsg = '', 3000);
  }

  async function saveCrew() {
    crewMsg = 'Alterando...';
    const res = await luna.setCrewMode(crewEnabled);
    crewMsg = res?.message || 'Erro';
    setTimeout(() => crewMsg = '', 3000);
  }

  async function saveModel() {
    modelMsg = 'Alterando...';
    const res = await luna.setWritingModel(writingModel);
    modelMsg = res?.message || 'Erro';
    setTimeout(() => modelMsg = '', 3000);
  }

  async function saveTtsProvider(provider: string) {
    ttsMsg = 'Alterando...';
    ttsCurrent = provider;
    const res = await luna.setTtsProvider(provider);
    ttsMsg = res?.success ? `TTS: ${provider}` : 'Erro';
    setTimeout(() => ttsMsg = '', 3000);
  }

  async function checkUpdate() {
    upd.checking = true;
    upd.result = '';
    const res = await luna.checkUpdate();
    if (res && !res.error) {
      upd = { ...upd, ...res, checking: false };
    } else {
      upd.checking = false;
      upd.result = 'Erro ao verificar atualizações';
    }
  }

  async function applyUpdate() {
    if (!confirm('Aplicar atualização? O backend será reiniciado.')) return;
    upd.applying = true;
    upd.result = '';
    const res = await luna.applyUpdate();
    if (res && res.success) {
      upd.result = '✅ Atualização aplicada! Reinicie o backend.';
      upd.update_available = false;
    } else {
      upd.result = '❌ ' + (res?.error || 'Falha ao atualizar');
    }
    upd.applying = false;
  }

  onMount(() => {
    loadMetrics();
    loadApps();
    loadFacts();
    loadPerf();
    loadModels();
    loadTts();

    const metricsInterval = setInterval(loadMetrics, 3000);
    const perfInterval = setInterval(loadPerf, 10000);

    return () => {
      clearInterval(metricsInterval);
      clearInterval(perfInterval);
    };
  });
</script>

<div class="panel-view">
  <div class="panel-header">
    <Icon name="activity" />
    <h2>Sistema</h2>
  </div>
  <div class="panel-body">
    <!-- Bloco 1: Métricas -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="activity" size="14" />
        <span>Métricas em Tempo Real</span>
        <button class="btn-icon" onclick={loadMetrics} title="Atualizar">
          <Icon name="refresh-cw" size="12" />
        </button>
      </div>
      <div class="metrics-grid">
        <div class="card metric-card">
          <div class="card-label">CPU</div>
          <div class="metric-val">{metrics.cpu_percent}%</div>
          <div class="progress"><div class="progress-fill" style="width: {metrics.cpu_percent}%"></div></div>
        </div>
        <div class="card metric-card">
          <div class="card-label">RAM</div>
          <div class="metric-val">{metrics.ram_percent}%</div>
          <div class="progress"><div class="progress-fill" style="width: {metrics.ram_percent}%"></div></div>
        </div>
        <div class="card metric-card">
          <div class="card-label">Disco</div>
          <div class="metric-val">{metrics.disk_percent}%</div>
          <div class="progress"><div class="progress-fill" style="width: {metrics.disk_percent}%"></div></div>
        </div>
        <div class="card metric-card">
          <div class="card-label">Uso RAM (GB)</div>
          <div class="metric-val text-sm">{metrics.ram_used_gb.toFixed(1)} / {metrics.ram_total_gb.toFixed(1)} GB</div>
        </div>
      </div>
    </div>

    <!-- Bloco 2: Apps -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="grid" size="14" />
        <span>Aplicativos</span>
      </div>
      <div class="card">
        <div class="apps-list">
          {#each apps as app}
            <button class="tag" onclick={() => { openAppName = app; }}>{app}</button>
          {/each}
        </div>
        <div class="input-row">
          <input class="field" bind:value={openAppName} placeholder="Nome do app para abrir..." />
          <button class="btn primary sm" onclick={() => openApp(openAppName)}>
            <Icon name="external-link" size="14" /> Abrir
          </button>
        </div>
      </div>
    </div>

    <!-- Bloco 3: Fatos/Memória -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="brain" size="14" />
        <span>Memória Persistente</span>
        <span class="facts-header-tag">{factsHeader}</span>
      </div>
      <div class="card">
        <div class="facts-list">
          {#if facts.length === 0}
            <div class="no-data">Nenhum fato salvo na memória persistente.</div>
          {:else}
            {#each facts as fact}
              <div class="fact-item">
                <span class="fact-text">{fact.fact}</span>
                <span class="fact-cat">{fact.category || 'geral'}</span>
              </div>
            {/each}
          {/if}
        </div>
        <div class="btn-row">
          <button class="btn sm" onclick={loadFacts}>
            <Icon name="refresh-cw" size="14" /> Recarregar
          </button>
          <button class="btn danger sm" onclick={clearFacts}>
            <Icon name="trash-2" size="14" /> Limpar Memória
          </button>
        </div>
      </div>
    </div>

    <!-- Bloco 4: Performance -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="zap" size="14" />
        <span>Performance & Cache</span>
      </div>
      <div class="card">
        <div class="perf-row">
          <span class="perf-label">Tempo médio de resposta</span>
          <span class="perf-val">{Math.round(perfInfo.avg_request_ms)} ms</span>
        </div>
        <div class="perf-row">
          <span class="perf-label">Cache Hits / Misses</span>
          <span class="perf-val">
            {perfInfo.cache_hits} / {perfInfo.cache_misses} 
            ({perfInfo.cache_hits + perfInfo.cache_misses > 0 ? Math.round((perfInfo.cache_hits / (perfInfo.cache_hits + perfInfo.cache_misses)) * 100) : 0}%)
          </span>
        </div>
        <div class="perf-row">
          <span class="perf-label">Entradas em cache</span>
          <span class="perf-val">{perfInfo.total_entries}</span>
        </div>
        <div class="btn-row" style="margin-top: 10px;">
          <button class="btn sm" onclick={loadPerf}>
            <Icon name="refresh-cw" size="14" /> Atualizar
          </button>
          <button class="btn danger sm" onclick={resetAll} style="margin-left: auto;">
            <Icon name="skull" size="14" /> Limpeza Total
          </button>
        </div>
      </div>
    </div>

    <!-- Bloco 5: Modelos LLM -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="cpu" size="14" />
        <span>Provedores de IA</span>
        <button class="btn-icon" onclick={loadModels} title="Atualizar">
          <Icon name="refresh-cw" size="12" />
        </button>
      </div>
      <div class="card">
        <div class="provider-list">
          {#each providers as p}
            <div class="provider-item" class:inactive={!p.active}>
              <div class="provider-row">
                <span class="provider-name">{p.name}</span>
                {#if p.available}
                  <span class="status-dot active" title="Disponível"></span>
                {:else if p.active}
                  <span class="status-dot busy" title="Rate limited ({p.rate_limited_for}s)"></span>
                {:else}
                  <span class="status-dot inactive" title="Inativo"></span>
                {/if}
              </div>
              {#if p.model}
                <div class="provider-model">{p.model}</div>
              {/if}
              {#if p.models}
                {#each Object.values(p.models) as m}
                  <div class="provider-model">
                    {m.name}
                    {#if m.rate_limited_for > 0}
                      <span class="rl-badge">⏳ {m.rate_limited_for}s</span>
                    {/if}
                  </div>
                {/each}
              {/if}
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- Bloco 5.5: Configurações -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="settings" size="14" />
        <span>Configurações</span>
      </div>
      <div class="card settings-card">
        <!-- Cascade Order -->
        <div class="setting-row">
          <span class="setting-label">Ordem dos provedores (cascade)</span>
          <div class="input-row">
            <input class="field" bind:value={cascadeOrder} placeholder="ex: puter,groq,gemini" />
            <button class="btn sm primary" onclick={saveCascade}>Salvar</button>
          </div>
          {#if cascadeMsg}<div class="setting-msg">{cascadeMsg}</div>{/if}
        </div>

        <!-- Crew Mode -->
        <div class="setting-row">
          <span class="setting-label">Crew Mode (múltiplos LLMs)</span>
          <div class="input-row">
            <label class="toggle">
              <input type="checkbox" bind:checked={crewEnabled} onchange={saveCrew} />
              <span class="toggle-slider"></span>
            </label>
            <span class="toggle-label">{crewEnabled ? 'Ativado' : 'Desativado'}</span>
          </div>
          {#if crewMsg}<div class="setting-msg">{crewMsg}</div>{/if}
        </div>

        <!-- Writing Model -->
        <div class="setting-row">
          <span class="setting-label">Modelo de escrita</span>
          <div class="input-row">
            <select class="field select" bind:value={writingModel} onchange={saveModel}>
              <option value="medium">Médio (rápido)</option>
              <option value="high">Alto (profundo)</option>
            </select>
          </div>
          {#if modelMsg}<div class="setting-msg">{modelMsg}</div>{/if}
        </div>

        <!-- TTS Provider -->
        <div class="setting-row">
          <span class="setting-label">Provedor de voz (TTS)</span>
          <div class="input-row tts-buttons">
            {#each ttsProviders as p}
              <button class="btn sm" class:primary={ttsCurrent === p} onclick={() => saveTtsProvider(p)}>
                {p}
                {#if ttsCurrent === p}<span class="check-mark">✓</span>{/if}
              </button>
            {/each}
          </div>
          {#if ttsMsg}<div class="setting-msg">{ttsMsg}</div>{/if}
        </div>

        <!-- TTS Voice -->
        {#if ttsVoices[ttsCurrent] && ttsVoices[ttsCurrent].length > 0}
          <div class="setting-row">
            <span class="setting-label">Voz TTS atual</span>
            <div class="setting-voice">{ttsVoice || ttsVoices[ttsCurrent][0]}</div>
            <div class="voice-list">
              {#each ttsVoices[ttsCurrent] as v}
                <span class="voice-tag" class:active={ttsVoice === v}>{v}</span>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <!-- Bloco 6: Atualizações -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="git-branch" size="14" />
        <span>Atualizações</span>
      </div>
      <div class="card">
        <div class="update-row">
          <span class="perf-label">Commit atual</span>
          <span class="perf-val mono">{upd.current || '---'}</span>
        </div>
        <div class="update-row">
          <span class="perf-label">Último commit</span>
          <span class="perf-val mono">{upd.latest || '---'}</span>
        </div>
        {#if upd.commits_ahead > 0}
          <div class="update-available-badge">
            {upd.commits_ahead} novo{upd.commits_ahead > 1 ? 's' : ''} commit{upd.commits_ahead > 1 ? 's' : ''} disponível{upd.commits_ahead > 1 ? 's' : ''}
          </div>
          <div class="commits-list">
            {#each upd.commits as c}
              <div class="commit-item">{c}</div>
            {/each}
          </div>
          <button class="btn primary sm" onclick={applyUpdate} disabled={upd.applying}>
            <Icon name="download" size="14" />
            {upd.applying ? 'Atualizando...' : 'Atualizar Agora'}
          </button>
        {:else if upd.current}
          <div class="update-ok">✓ Você está na versão mais recente</div>
        {:else if !upd.checking}
          <button class="btn sm" onclick={checkUpdate}>
            <Icon name="refresh-cw" size="14" /> Verificar atualizações
          </button>
        {:else}
          <div class="update-checking">Verificando...</div>
        {/if}
        {#if upd.result}
          <div class="update-result">{upd.result}</div>
        {/if}
      </div>
    </div>
  </div>
</div>

<style>
  .panel-view { flex: 1; display: flex; flex-direction: column; overflow: hidden; animation: fadeInUp 0.4s ease both; }
  .panel-header { display: flex; align-items: center; gap: 10px; padding: 16px 32px; flex-shrink: 0; }
  .panel-header h2 { font-size: 18px; font-weight: 600; color: rgba(255, 255, 255, 0.8); }
  .panel-header :global(svg) { color: var(--accent-blue); }
  .panel-body { flex: 1; overflow-y: auto; padding: 0 32px 32px; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 24px; max-width: 1400px; width: 100%; align-items: start; }
  .panel-section { display: flex; flex-direction: column; gap: 8px; }

  .section-title { font-size: 11px; font-weight: 700; color: rgba(255, 255, 255, 0.35); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
  .section-title :global(svg) { color: #8b5cf6; }

  .btn-row { display: flex; gap: 8px; margin-top: 4px; }
  .btn-icon { background: transparent; border: none; color: rgba(255,255,255,0.4); cursor: pointer; display: flex; align-items: center; transition: all 0.2s; }
  .btn-icon:hover { color: white; transform: rotate(45deg); }

  .card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 16px; padding: 18px; display: flex; flex-direction: column; gap: 14px; position: relative; overflow: hidden; backdrop-filter: blur(12px); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
  .card:hover { border-color: rgba(96, 165, 250, 0.25); transform: translateY(-2px); box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25); }

  /* Metrics Grid */
  .metrics-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .metric-card { padding: 14px; display: flex; flex-direction: column; gap: 6px; }
  .card-label { font-size: 11px; color: rgba(255,255,255,0.4); font-weight: 600; }
  .metric-val { font-size: 24px; font-weight: 800; color: white; font-family: 'JetBrains Mono', monospace; }
  .metric-val.text-sm { font-size: 13px; font-weight: 600; margin-top: 4px; }

  .progress { height: 4px; background: rgba(255,255,255,0.06); border-radius: 2px; overflow: hidden; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, #3b9eff, #8b5cf6); transition: width 0.5s ease-out; }

  /* Apps List */
  .apps-list { display: flex; flex-wrap: wrap; gap: 6px; max-height: 120px; overflow-y: auto; }
  .tag { padding: 6px 12px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: rgba(255,255,255,0.6); font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
  .tag:hover { background: rgba(59,158,255,0.1); border-color: rgba(59,158,255,0.25); color: #3b9eff; }

  .input-row { display: flex; gap: 8px; }
  .field { flex: 1; background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; color: white; font-size: 13px; padding: 10px 14px; outline: none; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
  .field:focus { border-color: rgba(59,158,255,0.35); box-shadow: 0 0 12px rgba(59,158,255,0.1); }

  .btn { display: flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.75); cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); font-size: 12px; font-weight: 500; padding: 8px 14px; }
  .btn:hover { background: rgba(255,255,255,0.06); color: white; border-color: rgba(255,255,255,0.12); transform: translateY(-0.5px); }
  .btn.primary { background: linear-gradient(135deg, #3b82f6, #8b5cf6); border: none; color: white; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2); }
  .btn.primary:hover { box-shadow: 0 6px 20px rgba(59, 130, 246, 0.35); }
  .btn.danger { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.15); color: #f87171; }
  .btn.danger:hover { background: rgba(239,68,68,0.18); color: white; }
  .btn.sm { font-size: 11px; padding: 6px 12px; }

  /* Facts List */
  .facts-header-tag { font-size: 10px; color: #a78bfa; background: rgba(167,139,250,0.12); padding: 2px 8px; border-radius: 20px; font-weight: 600; text-transform: none; margin-left: auto; letter-spacing: 0; }
  .facts-list { max-height: 200px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
  .fact-item { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 12px; background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.02); border-radius: 10px; }
  .fact-text { font-size: 12px; color: rgba(255,255,255,0.7); line-height: 1.4; }
  .fact-cat { font-size: 9px; font-weight: 600; color: #3b9eff; background: rgba(59,158,255,0.1); padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
  .no-data { font-size: 12px; color: rgba(255,255,255,0.3); text-align: center; padding: 12px; }

  /* Provider List */
  .provider-list { display: flex; flex-direction: column; gap: 6px; }
  .provider-item { padding: 10px 12px; background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.02); border-radius: 10px; }
  .provider-item.inactive { opacity: 0.45; }
  .provider-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .provider-name { font-size: 12px; color: rgba(255,255,255,0.75); font-weight: 600; }
  .provider-model { font-size: 10px; color: rgba(255,255,255,0.35); margin-top: 2px; font-family: 'JetBrains Mono', monospace; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .status-dot.active { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,0.4); }
  .status-dot.busy { background: #f59e0b; box-shadow: 0 0 8px rgba(245,158,11,0.4); }
  .status-dot.inactive { background: #6b7280; }
  .rl-badge { font-size: 9px; color: #f59e0b; margin-left: 6px; font-weight: 600; }

  /* Performance */
  .perf-row { display: flex; justify-content: space-between; align-items: center; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.03); }
  .perf-row:last-of-type { border-bottom: none; }
  .perf-label { font-size: 12px; color: rgba(255,255,255,0.4); }
  .perf-val { font-size: 12px; color: white; font-family: 'JetBrains Mono', monospace; font-weight: 600; }

  /* Update */
  .update-row { display: flex; justify-content: space-between; align-items: center; padding-bottom: 6px; }
  .mono { font-family: 'JetBrains Mono', monospace; font-size: 11px; }
  .update-available-badge { background: rgba(34,197,94,0.12); color: #4ade80; font-size: 11px; font-weight: 600; padding: 4px 10px; border-radius: 20px; text-align: center; }
  .update-ok { color: rgba(255,255,255,0.3); font-size: 12px; text-align: center; padding: 8px; }
  .update-checking { color: rgba(255,255,255,0.4); font-size: 12px; text-align: center; padding: 8px; }
  .update-result { font-size: 11px; color: rgba(255,255,255,0.6); text-align: center; padding: 6px; background: rgba(0,0,0,0.15); border-radius: 8px; }
  .commits-list { max-height: 120px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; background: rgba(0,0,0,0.1); border-radius: 8px; padding: 6px; }
  .commit-item { font-size: 10px; color: rgba(255,255,255,0.5); font-family: 'JetBrains Mono', monospace; padding: 2px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* Settings */
  .settings-card { gap: 16px; }
  .setting-row { display: flex; flex-direction: column; gap: 8px; padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .setting-row:last-of-type { border-bottom: none; padding-bottom: 0; }
  .setting-label { font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.5); }
  .setting-msg { font-size: 10px; color: #22c55e; margin-top: -4px; }
  .setting-voice { font-size: 12px; color: rgba(255,255,255,0.7); font-family: 'JetBrains Mono', monospace; }
  .select { appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 10px center; padding-right: 32px; cursor: pointer; }
  .tts-buttons { flex-wrap: wrap; gap: 6px; }
  .check-mark { margin-left: 4px; font-size: 10px; }
  .voice-list { display: flex; flex-wrap: wrap; gap: 4px; }
  .voice-tag { font-size: 10px; padding: 3px 8px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; color: rgba(255,255,255,0.4); }
  .voice-tag.active { background: rgba(59,158,255,0.1); border-color: rgba(59,158,255,0.2); color: #3b9eff; }
  .toggle { position: relative; display: inline-block; width: 36px; height: 20px; cursor: pointer; }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .toggle-slider { position: absolute; inset: 0; background: rgba(255,255,255,0.1); border-radius: 20px; transition: all 0.3s; }
  .toggle-slider::before { content: ''; position: absolute; height: 14px; width: 14px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: all 0.3s; }
  .toggle input:checked + .toggle-slider { background: #3b9eff; }
  .toggle input:checked + .toggle-slider::before { transform: translateX(16px); }
  .toggle-label { font-size: 11px; color: rgba(255,255,255,0.5); }
</style>
