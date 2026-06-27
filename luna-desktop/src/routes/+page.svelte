<script lang="ts">
  import Sidebar from '$lib/components/Sidebar.svelte';
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
        {#if luna.messages.length > 0}
          <div class="greeting">
            <span class="greeting-sub">Olá, eu sou a</span>
            <h1 class="greeting-title">LUNA</h1>
            <p class="greeting-desc">Como posso te ajudar hoje?</p>
          </div>
        {/if}
        <div class="header-right">
          <div class="conn-badge" class:connected={luna.connected}>
            <span class="conn-dot"></span>
            <span class="conn-label">{luna.connected ? 'Conectado' : 'Offline'}</span>
          </div>
          <button
            class="voice-badge glass-panel"
            class:on={luna.voiceEnabled}
            onclick={() => luna.toggleVoiceInput()}
            title={luna.voiceEnabled ? 'Voz ativada' : 'Voz desativada'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            </svg>
          </button>
          <div class="mode-badge glass-panel">
            <img src="/logo.png" alt="Luna" style="width:18px;height:18px;object-fit:contain;margin-right:4px;" />
            <div class="mode-text">
              <span class="mode-title">Luna AI</span>
              <span class="mode-desc">{luna.currentMode === 'think' ? 'Modo Pensar' : luna.currentMode === 'analyze' ? 'Modo Analisar' : luna.currentMode === 'create' ? 'Modo Criar' : 'Modo Normal'}</span>
            </div>
          </div>
          <button class="settings-btn glass-panel" onclick={() => activeTab = 'system'} title="Configurações">⚙️</button>
        </div>
      </header>

      <div class="chat-area">
        {#if luna.messages.length === 0}
          <div class="nexus-container">
            <div class="nexus-orb">
              <img src="/logo.png" alt="Luna" class="nexus-logo" />
              <div class="nexus-ring r1"></div>
              <div class="nexus-ring r2"></div>
              <div class="nexus-ring r3"></div>
            </div>
            <h1 class="nexus-title">LUNA</h1>
            <p class="nexus-sub">Sistemas online · Pronta para ajudar</p>
            <div class="nexus-voice-status" class:on={luna.voiceEnabled}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
              <span>{luna.voiceEnabled ? 'Comando de voz ativo' : 'Comando de voz desativado'}</span>
            </div>
          </div>
        {:else}
          <ChatPanel messages={luna.messages} isTyping={luna.isTyping} currentAction={luna.currentAction} onSpeak={(t) => luna.speakMessage(t)} />
        {/if}
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
          <div class="nexus-container" style="padding-bottom:0">
            <div class="nexus-orb">
              <img src="/logo.png" alt="Luna" class="nexus-logo" />
              <div class="nexus-ring r1"></div>
              <div class="nexus-ring r2"></div>
              <div class="nexus-ring r3"></div>
            </div>
            <p class="status-label" class:active={luna.status !== 'idle'}>{statusLabels[luna.status]}</p>
            <button class="big-mic-btn" class:recording={luna.status === 'listening'} onclick={() => luna.toggleMic()}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
              {luna.status === 'listening' ? 'Parar' : 'Falar'}
            </button>
            <div class="nexus-voice-status" class:on={luna.voiceEnabled}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
              <span>{luna.voiceEnabled ? 'Comando de voz ativo' : 'Comando de voz desativado'}</span>
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

  .header { display:flex; justify-content:space-between; align-items:flex-start; padding:12px 40px 0; animation:fadeInUp 0.5s ease both; flex-shrink:0; position:relative; z-index:10; }
  .greeting { display:flex; flex-direction:column; gap:2px; }
  .greeting-sub { font-size:13px; color:rgba(255,255,255,0.45); font-weight:400; }
  .greeting-title {
    font-family:'Outfit','Inter',sans-serif; font-size:42px; font-weight:700;
    background:linear-gradient(135deg,#6ec6ff 0%,#3b9eff 50%,#a78bfa 100%);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; line-height:1.1;
  }
  .greeting-desc { font-size:14px; color:rgba(148,163,184,0.7); margin-top:4px; }
  .header-right { display:flex; align-items:center; gap:12px; }

  .glass-panel {
    background: rgba(15,18,36,0.55) !important;
    backdrop-filter: blur(20px) saturate(1.4) !important;
    -webkit-backdrop-filter: blur(20px) saturate(1.4) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.06) !important;
  }

  .mode-badge { display:flex; align-items:center; gap:10px; padding:10px 16px; border-radius:14px; }
  .mode-text { display:flex; flex-direction:column; gap:1px; }
  .mode-title { font-size:12px; font-weight:600; color:rgba(255,255,255,0.85); }
  .mode-desc { font-size:10px; color:rgba(255,255,255,0.4); }
  .settings-btn { width:40px; height:40px; border:none; border-radius:12px; font-size:18px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all 0.3s; }
  .settings-btn:hover { transform:rotate(90deg); background:rgba(255,255,255,0.08) !important; }

  .conn-badge { display:flex; align-items:center; gap:6px; padding:6px 12px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:10px; transition:all 0.3s; backdrop-filter:blur(16px); }
  .conn-badge.connected { border-color:rgba(34,197,94,0.2); background:rgba(34,197,94,0.06); }
  .conn-dot { width:7px; height:7px; border-radius:50%; background:rgba(255,255,255,0.2); transition:all 0.3s; }
  .conn-badge.connected .conn-dot { background:#22c55e; box-shadow:0 0 6px rgba(34,197,94,0.5); }
  .conn-label { font-size:11px; font-weight:500; color:rgba(255,255,255,0.4); transition:color 0.3s; }
  .conn-badge.connected .conn-label { color:rgba(34,197,94,0.8); }

  .voice-badge {
    width: 36px; height: 36px;
    border: none; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    color: rgba(255,255,255,0.25);
    transition: all 0.3s;
    font-size: 16px;
  }
  .voice-badge.on {
    color: #22c55e;
    background: rgba(34,197,94,0.1) !important;
    border-color: rgba(34,197,94,0.2) !important;
    box-shadow: 0 0 16px rgba(34,197,94,0.15);
  }
  .voice-badge.on svg { filter: drop-shadow(0 0 6px rgba(34,197,94,0.4)); }

  /* ── Nexus (idle screen) ── */
  .nexus-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    animation: fadeInUp 0.8s ease both;
    padding-bottom: 10vh;
  }
  .nexus-orb {
    position: relative;
    width: 100px;
    height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .nexus-logo {
    width: 72px;
    height: 72px;
    object-fit: contain;
    border-radius: 50%;
    z-index: 2;
    animation: nexusPulse 3s ease-in-out infinite;
    filter: drop-shadow(0 0 20px rgba(59,158,255,0.3));
  }
  .nexus-ring {
    position: absolute;
    border-radius: 50%;
    border: 1.5px solid rgba(59,158,255,0.15);
    animation: nexusSpin 8s linear infinite;
  }
  .nexus-ring.r1 { width: 100px; height: 100px; }
  .nexus-ring.r2 { width: 130px; height: 130px; animation-duration: 12s; animation-direction: reverse; border-color: rgba(139,92,246,0.12); }
  .nexus-ring.r3 { width: 160px; height: 160px; animation-duration: 16s; border-color: rgba(34,197,94,0.08); }
  .nexus-title {
    font-family: 'Outfit', 'Inter', sans-serif;
    font-size: 48px;
    font-weight: 700;
    background: linear-gradient(135deg, #6ec6ff 0%, #3b9eff 50%, #a78bfa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.1;
    margin: 0;
    letter-spacing: 0.05em;
  }
  .nexus-sub {
    font-size: 14px;
    color: rgba(148,163,184,0.5);
    margin: 0;
    font-weight: 400;
  }
  .nexus-voice-status {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 12px;
    color: rgba(255,255,255,0.25);
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    transition: all 0.3s;
  }
  .nexus-voice-status.on {
    color: rgba(34,197,94,0.7);
    border-color: rgba(34,197,94,0.15);
    background: rgba(34,197,94,0.05);
  }
  .nexus-voice-status.on svg { color: #22c55e; }

  @keyframes nexusPulse {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.05); opacity: 0.85; }
  }
  @keyframes nexusSpin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .chat-area {
    flex: 1;
    overflow-y: auto;
    padding: 0 40px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .footer { padding:0 40px 24px; flex-shrink:0; position:relative; z-index:10; }

  .panel-view { flex:1; display:flex; flex-direction:column; overflow:hidden; animation:fadeInUp 0.4s ease both; position:relative; z-index:1; }
  .panel-body { flex:1; overflow-y:auto; padding:0 32px 32px; display:flex; flex-direction:column; gap:12px; }
  .panel-body.center { align-items:center; justify-content:center; }

  .status-label { font-size:15px; font-weight:500; color:rgba(255,255,255,0.35); letter-spacing:0.03em; transition:all 0.4s; }
  .status-label.active { color:var(--accent-blue); text-shadow:0 0 20px rgba(59,158,255,0.3); }

  .big-mic-btn { display:flex; align-items:center; justify-content:center; gap:10px; padding:16px 40px; border:none; border-radius:16px; background:rgba(59,158,255,0.15); color:#3b9eff; font-size:15px; font-weight:600; cursor:pointer; transition:all 0.3s; margin:0 auto; }
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
