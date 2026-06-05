<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();

  let lightStatus = $state('—');
  let schedHour = $state<number | null>(null);
  let schedMin = $state<number | null>(null);
  let schedState = $state('off');
  let schedDays = $state([
    { d: 0, name: 'Seg', active: false },
    { d: 1, name: 'Ter', active: false },
    { d: 2, name: 'Qua', active: false },
    { d: 3, name: 'Qui', active: false },
    { d: 4, name: 'Sex', active: false },
    { d: 5, name: 'Sáb', active: false },
    { d: 6, name: 'Dom', active: false },
  ]);
  let schedules = $state<any[]>([]);

  let ctrlNotes = $state<string[]>([]);
  let ctrlReminders = $state('Nenhum lembrete.');
  let ctrlTimers = $state('Nenhum timer ativo.');

  let processes = $state<any[]>([]);
  let processError = $state('');

  // ── Lights ──────────────────────────────────────────────
  async function checkLight() {
    const res = await luna.fetchLightsStatus();
    if (res) {
      lightStatus = res.error ? `Erro: ${res.error}` : res.on === true ? '🟡 Ligada' : res.on === false ? '⚫ Apagada' : '? Desconhecido';
    }
  }

  async function setLight(state: boolean) {
    const res = await luna.setLightsState(state);
    if (res) {
      lightStatus = res.result || '—';
    }
  }

  // ── Schedules ───────────────────────────────────────────
  async function loadSchedules() {
    const res = await luna.fetchSchedules();
    if (res && res.schedules) {
      schedules = res.schedules;
    }
  }

  async function addSchedule() {
    if (schedHour === null || schedHour < 0 || schedHour > 23) {
      alert('Hora inválida (0-23)');
      return;
    }
    const days = schedDays.filter(d => d.active).map(d => d.d);
    await luna.addSchedule(schedHour, schedMin || 0, schedState === 'on', days.length ? days : null);
    
    // Reset
    schedHour = null;
    schedMin = null;
    schedDays = schedDays.map(d => ({ ...d, active: false }));
    await loadSchedules();
  }

  async function removeSchedule(sid: string) {
    await luna.deleteSchedule(sid);
    await loadSchedules();
  }

  async function toggleSchedule(sid: string) {
    await luna.toggleSchedule(sid);
    await loadSchedules();
  }

  // ── Quick Summary ───────────────────────────────────────
  async function loadControlSummary() {
    const res = await luna.fetchControlSummary();
    if (res) {
      ctrlNotes = res.notes || [];
      ctrlReminders = res.reminders || 'Nenhum lembrete.';
      ctrlTimers = res.timers || 'Nenhum timer ativo.';
    }
  }

  // ── Processes ───────────────────────────────────────────
  async function loadProcesses() {
    const res = await luna.fetchProcesses();
    if (res) {
      if (res.error) {
        processError = res.error;
        processes = [];
      } else {
        processError = '';
        processes = res.processes || [];
      }
    }
  }

  async function killProcess(pid: number, name: string) {
    if (!confirm(`Encerrar "${name}" (PID ${pid})?`)) return;
    const res = await luna.killProcess(pid);
    if (res) {
      alert(res.message || JSON.stringify(res));
      await loadProcesses();
    }
  }

  onMount(() => {
    checkLight();
    loadSchedules();
    loadControlSummary();
    loadProcesses();
  });
</script>

<div class="panel-view">
  <div class="panel-header">
    <Icon name="home" />
    <h2>Central de Controle</h2>
  </div>
  <div class="panel-body">
    <!-- Bloco 1: Luzes -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="lightbulb" size="14" />
        <span>Controle de Iluminação</span>
      </div>
      <div class="card">
        <div class="card-row">
          <div>
            <div class="card-label">Luz da Sala</div>
            <div class="status-sub">{lightStatus}</div>
          </div>
          <div class="btn-group">
            <button class="btn primary sm" onclick={() => setLight(true)}>
              <Icon name="plus" size="12" /> Ligar
            </button>
            <button class="btn danger sm" onclick={() => setLight(false)}>
              <Icon name="minus" size="12" /> Apagar
            </button>
          </div>
        </div>
        <div class="btn-row">
          <button class="btn sm" onclick={checkLight}>
            <Icon name="refresh-cw" size="14" /> Atualizar Status
          </button>
        </div>
      </div>
    </div>

    <!-- Bloco 2: Agendamentos -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="calendar-clock" size="14" />
        <span>Agendamentos de Luz</span>
      </div>
      <div class="card">
        <div class="input-grid">
          <input class="field text-center" type="number" min="0" max="23" bind:value={schedHour} placeholder="HH" style="width: 60px" />
          <span class="colon">:</span>
          <input class="field text-center" type="number" min="0" max="59" bind:value={schedMin} placeholder="MM" style="width: 60px" />
          
          <select class="field" bind:value={schedState} style="flex: 1">
            <option value="off">Apagar</option>
            <option value="on">Ligar</option>
          </select>
          
          <button class="btn primary sm" onclick={addSchedule}>
            <Icon name="plus" size="14" />
          </button>
        </div>

        <div class="days-label">Dias (Vazio = Todos)</div>
        <div class="days-selector">
          {#each schedDays as day}
            <button class="day-btn" class:active={day.active} onclick={() => day.active = !day.active}>
              {day.name}
            </button>
          {/each}
        </div>

        <div class="btn-row">
          <button class="btn sm" onclick={loadSchedules}>
            <Icon name="refresh-cw" size="14" /> Atualizar Lista
          </button>
        </div>
      </div>

      <!-- Lista Agendamentos -->
      {#if schedules.length > 0}
        <div class="schedules-list" style="margin-top: 8px;">
          {#each schedules as s}
            <div class="sched-item">
              <div class="sched-info">
                <span class="sched-action" class:on={s.state}>
                  {s.state ? '💡 Ligar' : '🌑 Apagar'} {String(s.hour).padStart(2, '0')}:{String(s.minute).padStart(2, '0')}
                </span>
                <span class="sched-days">
                  {s.days ? s.days.map((d: number) => schedDays[d].name).join(', ') : 'todos os dias'}
                </span>
              </div>
              <div class="sched-actions">
                <button class="btn sm" onclick={() => toggleSchedule(s.id)}>
                  {s.enabled ? '⏸' : '▶'}
                </button>
                <button class="btn danger sm" onclick={() => removeSchedule(s.id)}>
                  <Icon name="trash-2" size="12" />
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Bloco 3: Resumo Rápido -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="file-text" size="14" />
        <span>Resumo Rápido</span>
      </div>
      <div class="card">
        <div class="summary-section">
          <div class="summary-title">Notas</div>
          {#if ctrlNotes.length === 0}
            <div class="summary-val">Nenhuma nota.</div>
          {:else}
            <div class="summary-list">
              {#each ctrlNotes as note, i}
                <div class="summary-item">
                  <span class="summary-idx">{i + 1}.</span>
                  <span class="summary-txt">{note}</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <div class="summary-divider"></div>

        <div class="summary-section">
          <div class="summary-title">Lembretes</div>
          <div class="summary-val">{ctrlReminders}</div>
        </div>

        <div class="summary-divider"></div>

        <div class="summary-section">
          <div class="summary-title">Timers</div>
          <div class="summary-val">{ctrlTimers}</div>
        </div>

        <div class="btn-row">
          <button class="btn sm" onclick={loadControlSummary}>
            <Icon name="refresh-cw" size="14" /> Atualizar
          </button>
        </div>
      </div>
    </div>

    <!-- Bloco 4: Processos -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="cpu" size="14" />
        <span>Processos do Sistema</span>
      </div>
      <div class="card">
        <div class="process-section">
          {#if processError}
            <div class="no-data danger">{processError}</div>
          {:else if processes.length === 0}
            <div class="no-data">Nenhum processo listado.</div>
          {:else}
            <div class="process-list">
              {#each processes as p}
                <div class="process-item">
                  <div class="p-info">
                    <span class="p-name">{p.name}</span>
                    <span class="p-pid">({p.pid})</span>
                  </div>
                  <div class="p-stats">
                    <span class="p-stat">{p.cpu}% CPU</span>
                    <span class="p-stat">{p.mem}% RAM</span>
                  </div>
                  <button class="btn danger sm icon-only" onclick={() => killProcess(p.pid, p.name)}>
                    <Icon name="trash-2" size="12" />
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
        <div class="btn-row">
          <button class="btn sm" onclick={loadProcesses}>
            <Icon name="refresh-cw" size="14" /> Atualizar Processos
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

  .card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 16px; padding: 18px; display: flex; flex-direction: column; gap: 14px; position: relative; overflow: hidden; backdrop-filter: blur(12px); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
  .card:hover { border-color: rgba(96, 165, 250, 0.25); transform: translateY(-2px); box-shadow: 0 12px 30px rgba(0, 0, 0, 0.25); }

  .card-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .card-label { font-size: 11px; color: rgba(255,255,255,0.45); font-weight: 600; }
  .status-sub { font-size: 12px; color: rgba(255,255,255,0.7); margin-top: 4px; }

  .btn-group { display: flex; gap: 6px; }
  .btn-row { display: flex; gap: 8px; }

  .btn { display: flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.75); cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); font-size: 12px; font-weight: 500; padding: 8px 14px; }
  .btn:hover { background: rgba(255,255,255,0.06); color: white; border-color: rgba(255,255,255,0.12); transform: translateY(-0.5px); }
  .btn:active { transform: scale(0.97); }
  .btn.primary { background: linear-gradient(135deg, #3b82f6, #8b5cf6); border: none; color: white; box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2); }
  .btn.primary:hover { box-shadow: 0 6px 20px rgba(59, 130, 246, 0.35); }
  .btn.danger { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.15); color: #f87171; }
  .btn.danger:hover { background: rgba(239,68,68,0.18); color: white; }
  .btn.sm { font-size: 11px; padding: 6px 12px; border-radius: 10px; }
  .btn.icon-only { width: 28px; height: 28px; padding: 0; }

  /* Input Grid */
  .input-grid { display: flex; gap: 6px; align-items: center; }
  .colon { color: rgba(255,255,255,0.3); font-size: 14px; }
  .field { background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; color: white; font-size: 13px; padding: 10px 14px; outline: none; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
  .field.text-center { text-align: center; }
  .field:focus { border-color: rgba(59,158,255,0.35); box-shadow: 0 0 12px rgba(59,158,255,0.1); }

  /* Days Selector */
  .days-label { font-size: 10px; color: rgba(255,255,255,0.3); text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }
  .days-selector { display: flex; gap: 4px; flex-wrap: wrap; }
  .day-btn { padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.4); font-size: 11px; cursor: pointer; transition: all 0.2s; }
  .day-btn:hover { background: rgba(255,255,255,0.05); color: white; }
  .day-btn.active { background: rgba(59,158,255,0.15); border-color: rgba(59,158,255,0.3); color: #3b9eff; font-weight: 600; }

  /* Schedules List */
  .schedules-list { display: flex; flex-direction: column; gap: 6px; }
  .sched-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: rgba(15,15,30,0.4); border: 1px solid rgba(255,255,255,0.03); border-radius: 12px; }
  .sched-info { display: flex; flex-direction: column; gap: 2px; }
  .sched-action { font-size: 12.5px; font-weight: 600; color: rgba(255,255,255,0.5); }
  .sched-action.on { color: #3b9eff; }
  .sched-days { font-size: 10.5px; color: rgba(255,255,255,0.3); }
  .sched-actions { display: flex; gap: 6px; }

  /* Summary Section */
  .summary-section { display: flex; flex-direction: column; gap: 6px; }
  .summary-title { font-size: 11px; font-weight: 700; color: #a78bfa; text-transform: uppercase; letter-spacing: 0.05em; }
  .summary-val { font-size: 12px; color: rgba(255,255,255,0.6); }
  .summary-divider { height: 1px; background: rgba(255,255,255,0.04); }
  .summary-list { display: flex; flex-direction: column; gap: 4px; }
  .summary-item { display: flex; gap: 8px; font-size: 12px; color: rgba(255,255,255,0.7); }
  .summary-idx { color: #3b9eff; font-weight: 600; }
  .summary-txt { flex: 1; }

  /* Processes */
  .process-section { max-height: 400px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
  .process-list { display: flex; flex-direction: column; gap: 6px; }
  .process-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: rgba(0,0,0,0.15); border-radius: 10px; border: 1px solid rgba(255,255,255,0.02); }
  .p-info { display: flex; gap: 6px; align-items: center; }
  .p-name { font-size: 12px; color: rgba(255,255,255,0.8); font-weight: 500; }
  .p-pid { font-size: 10px; color: rgba(255,255,255,0.3); font-family: 'JetBrains Mono', monospace; }
  .p-stats { font-size: 10.5px; color: rgba(255,255,255,0.4); display: flex; gap: 8px; font-family: 'JetBrains Mono', monospace; }
  .p-stat { background: rgba(255,255,255,0.02); padding: 2px 6px; border-radius: 4px; }
  .no-data { font-size: 12px; color: rgba(255,255,255,0.3); text-align: center; padding: 12px; }
  .no-data.danger { color: #ef4444; background: rgba(239,68,68,0.05); border-radius: 8px; border: 1px solid rgba(239,68,68,0.15); }
</style>
