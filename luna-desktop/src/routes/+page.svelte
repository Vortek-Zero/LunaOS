<script lang="ts">
  import Sidebar from '$lib/components/Sidebar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Orb from '$lib/components/Orb.svelte';
  import ChatInput from '$lib/components/ChatInput.svelte';
  import ChatPanel from '$lib/components/ChatPanel.svelte';
  import StarField from '$lib/components/StarField.svelte';
  import MediaPanel from '$lib/components/MediaPanel.svelte';
  import SystemPanel from '$lib/components/SystemPanel.svelte';
  import ControlPanel from '$lib/components/ControlPanel.svelte';
  import WikiPanel from '$lib/components/WikiPanel.svelte';
  import CodingPanel from '$lib/components/CodingPanel.svelte';
  import WritingPanel from '$lib/components/WritingPanel.svelte';

  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();
  let activeTab = $state('chat');

  const statusLabels: Record<string, string> = {
    idle: 'Pronta para ajudar',
    listening: 'Ouvindo você...',
    thinking: 'Pensando...',
    executing: 'Executando...',
    speaking: 'Falando...',
  };

  $effect(() => { luna.checkConnection(); });

  async function handleWindowAction(action: 'minimize' | 'maximize' | 'close') {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      const win = getCurrentWindow();
      if (action === 'minimize') await win.minimize();
      else if (action === 'maximize') await win.toggleMaximize();
      else if (action === 'close') {
        try { await luna.shutdownBackend(); } catch {}
        await win.close();
      }
    } catch (e) {
      console.warn('Window action failed (Tauri only):', e);
    }
  }

  function selectWikiCommand(cmd: string) {
    activeTab = 'chat';
    luna.sendMessage(cmd);
  }

  function handleMode(mode: string, prompt: string) {
    luna.sendWithMode(mode, prompt);
  }
</script>

<div class="app-shell">
  <StarField />
  <Sidebar bind:activeTab />

  <main class="main-content" class:no-padding={activeTab === 'coding' || activeTab === 'write' || activeTab === 'joy'}>
    <div class="titlebar" data-tauri-drag-region>
      <div class="window-controls">
        <button class="win-btn" onclick={() => handleWindowAction('minimize')} title="Minimizar">─</button>
        <button class="win-btn" onclick={() => handleWindowAction('maximize')} title="Maximizar">□</button>
        <button class="win-btn close" onclick={() => handleWindowAction('close')} title="Fechar">✕</button>
      </div>
    </div>

    {#if activeTab === 'chat'}
      <header class="header">
        <div class="header-right">
          <div class="conn-badge" class:connected={luna.connected}>
            <span class="conn-dot"></span>
            <span class="conn-label">{luna.connected ? 'Conectado' : 'Offline'}</span>
          </div>
          <button
            class="voice-badge glass-panel"
            class:on={luna.ttsEnabled}
            onclick={() => luna.toggleTts()}
            title={luna.ttsEnabled ? 'Fala automática ativada' : 'Fala automática desativada'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
          </button>
          <div class="mode-badge glass-panel">
            <img src="/logo.png" alt="Luna" style="width:18px;height:18px;object-fit:contain;margin-right:4px;" />
            <div class="mode-text">
              <span class="mode-title">Luna AI</span>
              <span class="mode-desc">{luna.currentMode === 'think' ? 'Modo Pensar' : luna.currentMode === 'analyze' ? 'Modo Analisar' : luna.currentMode === 'create' ? 'Modo Criar' : 'Modo Normal'}</span>
            </div>
          </div>
          <button class="settings-btn glass-panel" onclick={() => activeTab = 'system'} title="Configurações"><Icon name="settings" size="16" /></button>
        </div>
      </header>

      <div class="orb-anchor" class:shrunk={luna.messages.length > 0}>
        <Orb status={luna.status} audioLevel={luna.audioLevel} processingHeat={luna.processingHeat} mini={luna.messages.length > 0} />
        <p class="status-label" class:active={luna.status !== 'idle'}>
          {luna.status === 'executing' && luna.currentAction ? luna.currentAction : statusLabels[luna.status]}
        </p>
        <div class="nexus-voice-status" class:on={luna.ttsEnabled} onclick={() => luna.toggleTts()}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
          <span>{luna.ttsEnabled ? 'Fala automática' : 'Fala desativada'}</span>
        </div>
      </div>

      <div class="chat-area">
        <ChatPanel messages={luna.messages} isTyping={luna.isTyping} currentAction={luna.currentAction} onSpeak={(t) => luna.speakMessage(t)} />
      </div>

      <footer class="footer">
        <ChatInput
          onSend={(t) => luna.sendMessage(t)}
          onMic={() => luna.toggleMic()}
          onMode={(mode, prompt) => handleMode(mode, prompt)}
          isRecording={luna.status === 'listening'}
        />
      </footer>

    {:else if activeTab === 'voice'}
      <div class="panel-view">
        <div class="panel-body center">
          <div class="orb-section compact">
            <Orb status={luna.status} audioLevel={luna.audioLevel} processingHeat={luna.processingHeat} mini={true} />
            <p class="status-label" class:active={luna.status !== 'idle'}>{statusLabels[luna.status]}</p>
          </div>
          <button class="big-mic-btn" class:recording={luna.status === 'listening'} onclick={() => luna.toggleMic()}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
            {luna.status === 'listening' ? 'Parar' : 'Falar'}
          </button>
          <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;justify-content:center">
            <div class="nexus-voice-status" class:on={luna.voiceEnabled}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
              <span>{luna.voiceEnabled ? 'Escuta ativa' : 'Escuta desativada'}</span>
            </div>
            <div class="nexus-voice-status" class:on={luna.ttsEnabled} onclick={() => luna.toggleTts()}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
              <span>{luna.ttsEnabled ? 'Fala automática' : 'Fala desativada'}</span>
            </div>
          </div>
        </div>
      </div>

    {:else if activeTab === 'media'}
      <MediaPanel />
    {:else if activeTab === 'system'}
      <SystemPanel />
    {:else if activeTab === 'control'}
      <ControlPanel />
    {:else if activeTab === 'wiki'}
      <WikiPanel onSelectCommand={selectWikiCommand} />
    {:else if activeTab === 'coding'}
      <CodingPanel />
    {:else if activeTab === 'write'}
      <WritingPanel />
    {:else if activeTab === 'joy'}
      <div class="panel-view no-padding" style="width:100%;height:100%;overflow:hidden;display:flex;flex:1;">
        <iframe src="http://localhost:5050/joy" style="width:100%;height:100%;border:none;background:var(--bg-primary);" title="Joy Games"></iframe>
      </div>
    {/if}
  </main>
</div>

<style>
  .app-shell {
    display: flex;
    width: 100vw;
    height: 100vh;
    background: var(--bg-primary);
    overflow: hidden;
    border-radius: 12px;
    position: relative;
  }
  .app-shell::before, .app-shell::after {
    content: '';
    position: absolute;
    width: 500px; height: 500px;
    border-radius: 50%;
    filter: blur(140px);
    z-index: 0;
    pointer-events: none;
    opacity: 0.10;
    mix-blend-mode: screen;
  }
  .app-shell::before {
    background: radial-gradient(circle, #3b82f6 0%, transparent 70%);
    top: -100px; left: 20%;
    animation: floatGlowLeft 22s infinite ease-in-out;
  }
  .app-shell::after {
    background: radial-gradient(circle, #8b5cf6 0%, transparent 70%);
    bottom: -100px; right: 15%;
    animation: floatGlowRight 26s infinite ease-in-out;
  }

  .main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
    z-index: 1;
  }
  .main-content.no-padding { background: var(--bg-primary); }

  .titlebar { height:36px; display:flex; justify-content:flex-end; align-items:center; padding:0 12px; -webkit-app-region:drag; flex-shrink:0; z-index:50; }
  .window-controls { display:flex; gap:8px; -webkit-app-region:no-drag; }
  .win-btn { width:28px; height:28px; border:none; border-radius:8px; background:rgba(255,255,255,0.03); color:rgba(255,255,255,0.4); font-size:11px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all 0.2s; }
  .win-btn:hover { background:rgba(255,255,255,0.08); color:rgba(255,255,255,0.9); }
  .win-btn.close:hover { background:rgba(239,68,68,0.25); color:#f87171; }

  .header {
    display:flex; justify-content:flex-end; align-items:center;
    padding:8px 32px; flex-shrink:0; position:relative; z-index:10;
    animation:fadeInUp 0.5s ease both;
  }

  .header-right { display:flex; align-items:center; gap:10px; }

  .glass-panel {
    background: rgba(15,18,36,0.55) !important;
    backdrop-filter: blur(20px) saturate(1.4) !important;
    -webkit-backdrop-filter: blur(20px) saturate(1.4) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.06) !important;
  }

  .mode-badge { display:flex; align-items:center; gap:10px; padding:8px 14px; border-radius:12px; }
  .mode-text { display:flex; flex-direction:column; gap:1px; }
  .mode-title { font-size:11px; font-weight:600; color:rgba(255,255,255,0.85); }
  .mode-desc { font-size:9px; color:rgba(255,255,255,0.4); }
  .settings-btn { width:36px; height:36px; border:none; border-radius:10px; font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:background 0.3s; }
  .settings-btn:hover { background:rgba(255,255,255,0.08) !important; }
  .settings-btn:hover :global(svg) { transform:rotate(90deg); transition:transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1); }

  .conn-badge { display:flex; align-items:center; gap:6px; padding:5px 10px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:8px; transition:all 0.3s; backdrop-filter:blur(16px); }
  .conn-badge.connected { border-color:rgba(34,197,94,0.2); background:rgba(34,197,94,0.06); }
  .conn-dot { width:6px; height:6px; border-radius:50%; background:rgba(255,255,255,0.2); transition:all 0.3s; }
  .conn-badge.connected .conn-dot { background:#22c55e; box-shadow:0 0 6px rgba(34,197,94,0.5); }
  .conn-label { font-size:10px; font-weight:500; color:rgba(255,255,255,0.4); transition:color 0.3s; }
  .conn-badge.connected .conn-label { color:rgba(34,197,94,0.8); }

  .voice-badge {
    width:34px; height:34px;
    border: none; border-radius:8px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    color: rgba(255,255,255,0.25);
    transition: all 0.3s;
  }
  .voice-badge.on {
    color: #22c55e;
    background: rgba(34,197,94,0.1) !important;
    border-color: rgba(34,197,94,0.2) !important;
    box-shadow: 0 0 16px rgba(34,197,94,0.15);
  }

  /* ── Orb Anchor ── */
  .orb-anchor {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    transition: all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
    padding: 5vh 0 2vh;
    position: relative;
    z-index: 2;
    min-height: 200px;
  }
  .orb-anchor.shrunk {
    flex: 0 0 120px;
    min-height: 100px;
    padding: 8px 0;
    gap: 4px;
  }
  .orb-anchor.shrunk .status-label { font-size: 11px; }
  .orb-anchor.shrunk .nexus-voice-status { display: none; }

  .status-label {
    font-size: 14px;
    font-weight: 500;
    color: rgba(255,255,255,0.35);
    letter-spacing: 0.03em;
    transition: all 0.4s;
    text-align: center;
  }
  .status-label.active {
    color: #3b9eff;
    text-shadow: 0 0 20px rgba(59,158,255,0.3);
  }

  .nexus-voice-status {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 16px;
    font-size: 11px;
    color: rgba(255,255,255,0.25);
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    transition: all 0.3s;
    cursor: pointer;
  }
  .nexus-voice-status.on {
    color: rgba(34,197,94,0.7);
    border-color: rgba(34,197,94,0.15);
    background: rgba(34,197,94,0.05);
  }
  .nexus-voice-status.on svg { color: #22c55e; }

  .chat-area {
    flex: 1;
    overflow-y: auto;
    padding: 60px 40px 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    animation: fadeInUp 0.4s ease both;
  }

  .footer { padding:16px 40px 24px; flex-shrink:0; position:relative; z-index:10; }

  .panel-view { flex:1; display:flex; flex-direction:column; overflow:hidden; animation:fadeInUp 0.4s ease both; position:relative; z-index:1; }
  .panel-body { flex:1; overflow-y:auto; padding:0 32px 32px; display:flex; flex-direction:column; gap:12px; }
  .panel-body.center { align-items:center; justify-content:center; }

  .orb-section { display:flex; flex-direction:column; align-items:center; gap:12px; }
  .orb-section.compact { gap:8px; }

  .big-mic-btn { display:flex; align-items:center; justify-content:center; gap:10px; padding:14px 36px; border:none; border-radius:14px; background:rgba(59,158,255,0.15); color:#3b9eff; font-size:14px; font-weight:600; cursor:pointer; transition:all 0.3s; margin:0 auto; }
  .big-mic-btn:hover { background:rgba(59,158,255,0.25); transform:scale(1.03); }
  .big-mic-btn.recording { background:rgba(239,68,68,0.15); color:#ef4444; }

  @keyframes floatGlowLeft {
    0%,100% { transform:translate(0,0) scale(1); }
    33% { transform:translate(60px,90px) scale(1.15); }
    66% { transform:translate(-40px,50px) scale(0.9); }
  }
  @keyframes floatGlowRight {
    0%,100% { transform:translate(0,0) scale(1.15); }
    50% { transform:translate(-70px,-60px) scale(0.9); }
  }
</style>
