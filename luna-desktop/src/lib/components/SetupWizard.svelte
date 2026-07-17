<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();

  let loading = $state(true);
  let name = $state('');
  let apis = $state<Record<string, string>>({});
  let apiFields = $state<Array<{ key: string; label: string; url: string; free: boolean }>>([]);
  let saving = $state(false);
  let error = $state('');

  onMount(async () => {
    if (localStorage.getItem('luna_setup_skipped')) {
      window.dispatchEvent(new CustomEvent('setup-close'));
      return;
    }
    const status = await luna.checkSetup();
    if (status?.configured) {
      window.dispatchEvent(new CustomEvent('setup-close'));
      return;
    }
    if (status?.name) name = status.name;
    if (status?.missing_apis) apiFields = status.missing_apis;
    loading = false;
  });

  async function save() {
    saving = true;
    error = '';
    const data: Record<string, string> = { name: name.trim() || 'Usuário' };
    for (const field of apiFields) {
      const val = apis[field.key]?.trim();
      if (val) data[field.key] = val;
    }
    const res = await luna.saveSetup(data);
    if (res?.success) {
      localStorage.removeItem('luna_setup_skipped');
      window.location.reload();
    } else {
      error = res?.error || 'Erro ao salvar';
    }
    saving = false;
  }

  function skip() {
    localStorage.setItem('luna_setup_skipped', '1');
    window.location.reload();
  }
</script>

<div class="setup-overlay">
  <div class="setup-card">
    {#if loading}
      <div class="setup-header"><p class="setup-sub">Carregando...</p></div>
    {:else}
      <div class="setup-header">
        <img src="/logo.png" alt="Luna" class="setup-logo" />
        <h1>Bem-vindo à Luna</h1>
        <p class="setup-sub">Configure seu nome e pelo menos uma API de IA.<br/><strong>Groq</strong> é gratuita e a mais recomendada.</p>
      </div>

      <label class="field-label">Seu nome</label>
      <input class="setup-input" type="text" bind:value={name} placeholder="Seu nome..." />

      <label class="field-label" style="margin-top:8px;">Chaves de API</label>
      <div class="api-list">
        {#each apiFields as field}
          <div class="api-field">
            <label class="api-label">
              <span>{field.label}</span>
              {#if field.free}
                <span class="free-badge">gratuita</span>
              {/if}
            </label>
            <div class="api-input-row">
              <input
                class="setup-input"
                type="password"
                value={apis[field.key] ?? ''}
                oninput={(e) => { apis[field.key] = (e.target as HTMLInputElement).value; }}
                placeholder="Chave da API"
              />
              {#if field.url}
                <a href={field.url} target="_blank" class="btn-icon" title="Obter key">
                  <Icon name="external-link" size="16" />
                </a>
              {/if}
            </div>
          </div>
        {/each}
      </div>

      {#if error}
        <div class="setup-error">{error}</div>
      {/if}

      <div class="setup-actions">
        <button class="btn ghost" onclick={skip}>Pular</button>
        <button class="btn primary" onclick={save} disabled={saving || !name.trim()}>
          {saving ? 'Salvando...' : 'Salvar'}
        </button>
      </div>
    {/if}
  </div>
</div>

<style>
  .setup-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(16px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    animation: fadeIn 0.3s ease;
  }
  .setup-card {
    background: var(--bg-surface, #1a1a2e);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 24px;
    padding: 32px;
    width: 90%;
    max-width: 460px;
    max-height: 85vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
    animation: slideUp 0.4s ease;
  }
  .setup-header { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .setup-logo { width: 64px; height: 64px; border-radius: 16px; }
  .setup-header h1 { font-size: 22px; font-weight: 700; color: white; margin: 0; }
  .setup-sub { font-size: 13px; color: rgba(255, 255, 255, 0.5); margin: 0; line-height: 1.5; }
  .field-label { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.08em; }
  .setup-input {
    width: 100%;
    padding: 12px 14px;
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    color: white;
    font-size: 14px;
    outline: none;
    box-sizing: border-box;
    transition: border-color 0.2s;
  }
  .setup-input:focus { border-color: rgba(59, 158, 255, 0.4); }
  .api-list { display: flex; flex-direction: column; gap: 10px; max-height: 300px; overflow-y: auto; padding-right: 4px; }
  .api-field { display: flex; flex-direction: column; gap: 4px; }
  .api-label { display: flex; align-items: center; gap: 6px; font-size: 11px; color: rgba(255,255,255,0.5); font-weight: 600; }
  .free-badge { font-size: 9px; background: rgba(34,197,94,0.12); color: #4ade80; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
  .api-input-row { display: flex; gap: 6px; align-items: center; }
  .api-input-row .setup-input { flex: 1; }
  .btn-icon { background: transparent; border: none; color: rgba(255,255,255,0.3); cursor: pointer; padding: 6px; border-radius: 6px; transition: all 0.2s; display: flex; align-items: center; flex-shrink: 0; }
  .btn-icon:hover { color: white; background: rgba(255,255,255,0.05); }
  .setup-error { color: #f87171; font-size: 12px; text-align: center; background: rgba(239,68,68,0.08); padding: 8px; border-radius: 8px; }
  .setup-actions { display: flex; gap: 10px; justify-content: flex-end; align-items: center; margin-top: 4px; }
  .btn { display: flex; align-items: center; gap: 6px; border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.75); cursor: pointer; transition: all 0.2s; font-size: 13px; font-weight: 500; padding: 10px 18px; }
  .btn:hover { background: rgba(255,255,255,0.08); color: white; }
  .btn.primary { background: linear-gradient(135deg, #3b82f6, #8b5cf6); border: none; color: white; min-width: 100px; justify-content: center; }
  .btn.primary:hover { box-shadow: 0 6px 20px rgba(59, 130, 246, 0.35); }
  .btn.ghost { background: transparent; border: none; color: rgba(255,255,255,0.3); }
  .btn.ghost:hover { color: rgba(255,255,255,0.6); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
</style>
