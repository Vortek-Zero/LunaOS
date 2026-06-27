<script lang="ts">
  let { onSend, onMic, onMode, isRecording = false } = $props<{
    onSend: (text: string) => void;
    onMic: () => void;
    onMode?: (mode: string, prompt: string) => void;
    isRecording?: boolean;
  }>();

  let inputText = $state('');
  let textarea: HTMLTextAreaElement;

  function autoResize() {
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey && inputText.trim()) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    if (!inputText.trim()) return;
    onSend(inputText.trim());
    inputText = '';
    if (textarea) {
      textarea.style.height = 'auto';
    }
  }

  function handleTag(label: string) {
    const text = inputText.trim();
    if (text) {
      onMode?.(label.toLowerCase(), text);
      inputText = '';
      if (textarea) textarea.style.height = 'auto';
    } else {
      onSend('/' + label.toLowerCase());
    }
  }

  const tags = [
    { icon: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z', label: 'Pensar', color: '#a78bfa' },
    { icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z', label: 'Analisar', color: '#22d3ee' },
    { icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z', label: 'Criar', color: '#fd9644' },
  ];
</script>

<div class="chat-bottom">
  <div class="input-bar">
    <textarea
      bind:this={textarea}
      bind:value={inputText}
      onkeydown={handleKeydown}
      oninput={autoResize}
      placeholder="Fale com a Luna... (Shift+Enter para nova linha)"
      class="chat-input"
      rows="1"
    ></textarea>
    <div class="input-actions">
      <button class="mic-btn" class:recording={isRecording} onclick={onMic} title={isRecording ? 'Parar' : 'Microfone'}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      </button>
      {#if inputText.trim()}
        <button class="send-btn" onclick={submit} title="Enviar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      {/if}
    </div>
  </div>

  <div class="tags-row">
    {#each tags as tag}
      <button class="tag" class:active={false} onclick={() => handleTag(tag.label)} style="--tag-color: {tag.color}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d={tag.icon}/>
        </svg>
        <span>{tag.label}</span>
      </button>
    {/each}
  </div>
</div>

<style>
  .chat-bottom {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    width: 100%;
    max-width: 640px;
    margin: 0 auto;
    animation: fadeInUp 0.6s ease 0.4s both;
  }

  .input-bar {
    width: 100%;
    display: flex;
    align-items: flex-end;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 4px 4px 4px 20px;
    transition: all 0.3s ease;
    animation: glowPulse 4s ease-in-out infinite;
  }

  .input-bar:focus-within {
    border-color: rgba(59,158,255,0.3);
    background: rgba(255,255,255,0.06);
    box-shadow: 0 0 40px rgba(59,158,255,0.15), 0 0 80px rgba(59,158,255,0.05);
  }

  .chat-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: rgba(255,255,255,0.85);
    font-size: 14px;
    font-family: 'Inter', sans-serif;
    font-weight: 400;
    resize: none;
    overflow-y: hidden;
    line-height: 1.5;
    padding: 8px 0;
    min-height: 38px;
    max-height: 160px;
  }

  .chat-input::placeholder { color: rgba(255,255,255,0.2); }

  .input-actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
    align-self: flex-end;
    padding-bottom: 4px;
  }

  .mic-btn {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: rgba(255,255,255,0.06);
    border: none;
    color: rgba(255,255,255,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.25s ease;
  }

  .mic-btn:hover {
    background: rgba(59,158,255,0.15);
    color: #3b9eff;
  }

  .mic-btn.recording {
    background: rgba(239,68,68,0.15);
    color: #ef4444;
    animation: micPulse 1.5s infinite;
  }

  .send-btn {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: linear-gradient(135deg, #3b9eff, #8b5cf6);
    border: none;
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.25s ease;
    box-shadow: 0 4px 15px rgba(59,158,255,0.3);
  }

  .send-btn:hover {
    box-shadow: 0 6px 20px rgba(59,158,255,0.5);
    transform: translateY(-1px);
  }

  .send-btn:active { transform: scale(0.95); }

  .tags-row {
    display: flex;
    gap: 8px;
  }

  .tag {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    color: rgba(255,255,255,0.35);
    font-size: 12px;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.25s ease;
  }

  .tag:hover {
    background: color-mix(in srgb, var(--tag-color, #3b9eff) 10%, transparent);
    border-color: color-mix(in srgb, var(--tag-color, #3b9eff) 25%, transparent);
    color: var(--tag-color, #3b9eff);
  }

  .tag:active { transform: scale(0.96); }
</style>
