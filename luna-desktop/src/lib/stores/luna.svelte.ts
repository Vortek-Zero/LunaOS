// Luna API client — full backend integration
// Connects to the Python FastAPI server at localhost:5050

export interface ChatMessage {
  id: string;
  sender: 'luna' | 'user';
  text: string;
  timestamp: number;
}

const API = 'http://localhost:5050';

// Helper: fetch with self-signed cert tolerance
async function api(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts.headers },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── Reactive State ──────────────────────────────────────
let status = $state<'idle' | 'listening' | 'thinking' | 'executing' | 'speaking'>('idle');
let messages = $state<ChatMessage[]>([]);
let isTyping = $state(false);
let currentAction = $state('');
let audioLevel = $state(0);
let connected = $state(false);
let sessions = $state<any[]>([]);
let systemInfo = $state<any>({});
let mediaState = $state<any>({});
let voiceEnabled = $state(true);

let _id = 0;
function uid(): string { return `msg_${Date.now()}_${_id++}`; }

function addMessage(sender: 'luna' | 'user', text: string) {
  messages.push({ id: uid(), sender, text, timestamp: Date.now() });
}

// ── Chat (SSE — mostra pensando/executando em tempo real) ──
async function sendMessage(text: string) {
  if (!text.trim()) return;
  addMessage('user', text);
  status = 'thinking';
  isTyping = true;
  currentAction = 'Pensando...';

  try {
  const res = await fetch(`${API}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body?.getReader();
    if (!reader) throw new Error('Stream indisponível');

    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finalText = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        try {
          const data = JSON.parse(line.slice(5).trim());
          if (data.type === 'done') {
            finalText = data.text || '';
          } else if (data.type === 'error') {
            throw new Error(data.content || 'Erro no stream');
          } else if (data.type === 'thinking') {
            status = 'thinking';
            currentAction = data.label || 'Pensando...';
          } else if (data.type === 'tool_start') {
            status = 'executing';
            currentAction = data.label || 'Executando...';
          } else if (data.type === 'tool_done') {
            currentAction = data.label || 'Concluindo...';
          }
        } catch (e) {
          if (e instanceof SyntaxError) continue;
          throw e;
        }
      }
    }

    isTyping = false;
    currentAction = '';
    status = 'speaking';
    addMessage('luna', finalText || 'Sem resposta.');
    setTimeout(() => { status = 'idle'; }, 2500);
  } catch {
    isTyping = false;
    currentAction = '';
    status = 'idle';
    addMessage('luna', '⚠️ Erro de conexão. Verifique se o backend está rodando.');
  }
}

// ── Voice ───────────────────────────────────────────────
async function toggleMic() {
  if (status === 'listening') {
    status = 'idle';
    return;
  }
  status = 'listening';
  try {
    const data = await api('/api/voice/listen', { method: 'POST' });
    if (data.text) {
      addMessage('user', data.text);
      status = 'thinking';
      isTyping = true;
      const resp = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: data.text }),
      });
      isTyping = false;
      status = 'speaking';
      addMessage('luna', resp.response || 'Sem resposta.');
      // Speak
      try { await api('/api/voice/speak', { method: 'POST', body: JSON.stringify({ message: resp.response }) }); } catch {}
      setTimeout(() => { status = 'idle'; }, 1500);
    } else {
      status = 'idle';
    }
  } catch {
    status = 'idle';
    addMessage('luna', '⚠️ Falha na captura de áudio.');
  }
}

// ── Mode System (Pensar, Analisar, Criar) ──────────────
let currentMode = $state<'normal' | 'think' | 'analyze' | 'create'>('normal');

function setMode(mode: 'normal' | 'think' | 'analyze' | 'create') {
  currentMode = mode;
  if (mode === 'think') {
    addMessage('luna', '🤔 Modo **Pensar** ativado. Vou raciocinar passo a passo antes de responder.');
  } else if (mode === 'analyze') {
    addMessage('luna', '🔍 Modo **Analisar** ativado. Vou examinar telas, imagens e arquivos com atenção.');
  } else if (mode === 'create') {
    addMessage('luna', '✨ Modo **Criar** ativado. Vou usar toda minha inteligência para programar e gerar.');
  }
}

async function sendWithMode(mode: string, text: string) {
  if (mode === 'pensar') {
    setMode('think');
    await sendMessage(`[PENSAR] ${text}`);
  } else if (mode === 'analisar') {
    setMode('analyze');
    await sendMessage(`[ANALISAR] ${text}`);
  } else if (mode === 'criar') {
    setMode('create');
    addMessage('user', text);
    status = 'thinking';
    isTyping = true;
    currentAction = 'Gerando...';
    try {
      if (text.toLowerCase().includes('imagem') || text.toLowerCase().includes('arte') || text.toLowerCase().includes('cria') || text.toLowerCase().includes('design')) {
        const resp = await api('/api/code/chat', {
          method: 'POST',
          body: JSON.stringify({ message: `PROJETO VISUAL: ${text}`, current_code: '', session_id: 'create-mode' })
        });
        isTyping = false;
        currentAction = '';
        status = 'speaking';
        addMessage('luna', resp?.explanation || 'Pronto.');
        if (resp?.code) {
          addMessage('luna', `\`\`\`html\n${resp.code.slice(0, 3000)}\n\`\`\``);
        }
      } else {
        currentMode = 'create';
        const resp = await api('/api/code/chat', {
          method: 'POST',
          body: JSON.stringify({ message: `PROJETO: ${text}`, current_code: '', session_id: 'create-mode' })
        });
        isTyping = false;
        currentAction = '';
        status = 'speaking';
        addMessage('luna', resp?.explanation || 'Pronto.');
        if (resp?.code) {
          addMessage('luna', `\`\`\`html\n${resp.code.slice(0, 3000)}\n\`\`\``);
        }
      }
      setTimeout(() => { status = 'idle'; }, 2500);
    } catch {
      isTyping = false;
      currentAction = '';
      status = 'idle';
      addMessage('luna', '⚠️ Erro no modo Criar.');
    }
  }
}

// ── System Status ───────────────────────────────────────
async function checkConnection() {
  try {
    const data = await api('/api/status');
    connected = true;
    systemInfo = data;
  } catch {
    connected = false;
  }
}

async function resetSystem() {
  try { return await api('/api/system/reset', { method: 'DELETE' }); } catch { return null; }
}

async function fetchPerformance() {
  try { return await api('/api/performance'); } catch { return null; }
}

async function fetchSystemMetrics() {
  try { return await api('/api/system/metrics'); } catch { return null; }
}

async function fetchSystemFacts() {
  try { return await api('/api/system/facts'); } catch { return { facts: [] }; }
}

async function deleteSystemFacts() {
  try { await api('/api/system/facts', { method: 'DELETE' }); } catch {}
}

async function fetchSystemApps() {
  try { return await api('/api/system/apps'); } catch { return { apps: [] }; }
}

async function openSystemApp(name: string) {
  try { return await api('/api/system/apps/open', { method: 'POST', body: JSON.stringify({ text: name }) }); } catch { return null; }
}

// ── Control Center ──────────────────────────────────────
async function fetchLightsStatus() {
  try { return await api('/api/control/lights/status'); } catch { return null; }
}

async function setLightsState(state: boolean) {
  try { return await api('/api/control/lights', { method: 'POST', body: JSON.stringify({ state }) }); } catch { return null; }
}

async function fetchSchedules() {
  try { return await api('/api/control/lights/schedules'); } catch { return { schedules: [] }; }
}

async function addSchedule(hour: number, minute: number, state: boolean, days: number[] | null) {
  try { return await api('/api/control/lights/schedules', { method: 'POST', body: JSON.stringify({ hour, minute, state, days }) }); } catch { return null; }
}

async function deleteSchedule(sid: string) {
  try { return await api(`/api/control/lights/schedules/${sid}`, { method: 'DELETE' }); } catch { return null; }
}

async function toggleSchedule(sid: string) {
  try { return await api(`/api/control/lights/schedules/${sid}/toggle`, { method: 'PATCH' }); } catch { return null; }
}

async function fetchControlSummary() {
  try { return await api('/api/control/summary'); } catch { return null; }
}

async function fetchProcesses() {
  try { return await api('/api/control/processes'); } catch { return { processes: [] }; }
}

async function killProcess(pid: number) {
  try { return await api('/api/control/processes/kill', { method: 'POST', body: JSON.stringify({ pid }) }); } catch { return null; }
}

// ── Sessions ────────────────────────────────────────────
async function fetchSessions() {
  try {
    const data = await api('/api/sessions');
    sessions = data.sessions || [];
  } catch { sessions = []; }
}

async function createSession(title: string) {
  try {
    await api('/api/sessions', { method: 'POST', body: JSON.stringify({ title }) });
    await fetchSessions();
  } catch {}
}

async function deleteSession(id: string) {
  try {
    await api(`/api/sessions/${id}`, { method: 'DELETE' });
    await fetchSessions();
  } catch {}
}

async function switchSession(id: string) {
  try {
    const data = await api('/api/sessions/switch', { method: 'POST', body: JSON.stringify({ session_id: id }) });
    messages = [];
    // Load history
    const hist = await api(`/api/sessions/${id}/history`);
    if (hist.history) {
      for (const h of hist.history) {
        addMessage(h.role === 'user' ? 'user' : 'luna', h.content);
      }
    }
  } catch {}
}

// ── Media ───────────────────────────────────────────────
async function mediaControl(action: string, query?: string) {
  try {
    return await api('/api/media', { method: 'POST', body: JSON.stringify({ action, query }) });
  } catch { return null; }
}

// ── Memory ──────────────────────────────────────────────
async function getMemoryStats() {
  try { return await api('/api/memory/stats'); } catch { return null; }
}

async function getMemoryFacts() {
  try { return await api('/api/memory/facts'); } catch { return { facts: [] }; }
}

// ── Coding Mode ──────────────────────────────────────────
async function sendCodeChat(message: string, currentCode: string, sessionId: string) {
  try {
    return await api('/api/code/chat', {
      method: 'POST',
      body: JSON.stringify({ message, current_code: currentCode, session_id: sessionId })
    });
  } catch { return null; }
}

async function clearCodeSession(sessionId: string) {
  try { return await api(`/api/code/session/${sessionId}`, { method: 'DELETE' }); } catch { return null; }
}

// ── Write Mode ───────────────────────────────────────────
async function fetchWriteProjects() {
  try { return await api('/api/write/projects'); } catch { return { projects: [] }; }
}

async function createWriteProject(title: string, genre: string, style: string, characters: string[]) {
  try {
    return await api('/api/write/projects', {
      method: 'POST',
      body: JSON.stringify({ title, genre, style, characters })
    });
  } catch { return null; }
}

async function getWriteProject(projectId: string) {
  try { return await api(`/api/write/project/${projectId}`); } catch { return null; }
}

async function updateWriteProjectText(projectId: string, text: string) {
  try {
    return await api(`/api/write/project/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify({ text })
    });
  } catch { return null; }
}

async function addWriteChapter(projectId: string, title: string) {
  try {
    return await api(`/api/write/project/${projectId}/chapter`, {
      method: 'POST',
      body: JSON.stringify({ title })
    });
  } catch { return null; }
}

async function addWriteCharacter(projectId: string, name: string, age: number, traits: string, context: string, voice: string) {
  try {
    return await api(`/api/write/project/${projectId}/character`, {
      method: 'POST',
      body: JSON.stringify({ name, age, traits, context, voice })
    });
  } catch { return null; }
}

async function deleteWriteProject(projectId: string) {
  try { return await api(`/api/write/project/${projectId}`, { method: 'DELETE' }); } catch { return null; }
}

async function streamWrite(
  req: { prompt: string, project_id?: string, context_text?: string, style?: string, characters?: string, chapter?: number },
  onChunk: (text: string) => void,
  onPhase: (phase: string) => void,
  onDone: () => void,
  onError: (err: string) => void
) {
  try {
    const res = await fetch(`${API}/api/write/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reader = res.body?.getReader();
    if (!reader) throw new Error('Não foi possível obter o leitor do stream.');
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data:')) {
          try {
            const data = JSON.parse(line.slice(5).trim());
            if (data.type === 'text') onChunk(data.content);
            else if (data.type === 'phase') onPhase(data.content);
            else if (data.type === 'done') onDone();
            else if (data.type === 'error') onError(data.content);
          } catch {}
        }
      }
    }
  } catch (err: any) {
    onError(err.message || String(err));
  }
}

// ── Voice toggle ────────────────────────────────────────
async function toggleVoiceInput() {
  try { const d = await api('/api/voice/input/toggle', { method: 'POST' }); voiceEnabled = d.enabled; } catch {}
}

async function shutdownBackend() {
  try { await api('/api/shutdown', { method: 'POST' }); } catch {}
}

// ── Export ───────────────────────────────────────────────
export function useLuna() {
  return {
    get status() { return status; },
    set status(v) { status = v; },
    get messages() { return messages; },
    get isTyping() { return isTyping; },
    get currentAction() { return currentAction; },
    get audioLevel() { return audioLevel; },
    set audioLevel(v) { audioLevel = v; },
    get connected() { return connected; },
    get sessions() { return sessions; },
    get systemInfo() { return systemInfo; },
    get voiceEnabled() { return voiceEnabled; },
    get currentMode() { return currentMode; },
    sendMessage, toggleMic, addMessage, checkConnection, sendWithMode, setMode,
    fetchSessions, createSession, deleteSession, switchSession,
    mediaControl, getMemoryStats, getMemoryFacts, fetchPerformance,
    toggleVoiceInput, fetchSystemMetrics, fetchSystemFacts, deleteSystemFacts,
    resetSystem,
    fetchSystemApps, openSystemApp, fetchLightsStatus, setLightsState,
    fetchSchedules, addSchedule, deleteSchedule, toggleSchedule,
    fetchControlSummary, fetchProcesses, killProcess, sendCodeChat,
    clearCodeSession, fetchWriteProjects, createWriteProject, getWriteProject,
    updateWriteProjectText, addWriteChapter, addWriteCharacter, deleteWriteProject,
    streamWrite, shutdownBackend,
  };
}
