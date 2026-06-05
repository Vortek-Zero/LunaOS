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

  onMount(() => {
    loadMetrics();
    loadApps();
    loadFacts();
    loadPerf();

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
        <div class="btn-row">
          <button class="btn sm" onclick={loadPerf}>
            <Icon name="refresh-cw" size="14" /> Atualizar
          </button>
        </div>
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

  /* Performance */
  .perf-row { display: flex; justify-content: space-between; align-items: center; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.03); }
  .perf-row:last-of-type { border-bottom: none; }
  .perf-label { font-size: 12px; color: rgba(255,255,255,0.4); }
  .perf-val { font-size: 12px; color: white; font-family: 'JetBrains Mono', monospace; font-weight: 600; }
</style>
