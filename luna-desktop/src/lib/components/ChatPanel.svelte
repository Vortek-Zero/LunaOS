<script lang="ts">
  import type { ChatMessage } from '$lib/stores/luna.svelte';

  let { messages = [], isTyping = false, currentAction = '', onSpeak } = $props<{
    messages: ChatMessage[];
    isTyping: boolean;
    currentAction?: string;
    onSpeak?: (text: string) => void;
  }>();

  let chatContainer: HTMLDivElement;
  let copiedId = $state<string | null>(null);
  let speakingId = $state<string | null>(null);

  $effect(() => {
    if (messages.length && chatContainer) {
      requestAnimationFrame(() => {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      });
    }
  });

  function formatTime(ts: number): string {
    const d = new Date(ts);
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }

  async function copyMessage(id: string, text: string) {
    await navigator.clipboard.writeText(text);
    copiedId = id;
    setTimeout(() => { copiedId = null; }, 1500);
  }

  // Minimal markdown: **bold**, `code`, ```block```
  function renderMarkdown(text: string): string {
    // Code blocks first
    text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="code-block"><code>${escapeHtml(code.trim())}</code></pre>`
    );
    // Inline code
    text = text.replace(/`([^`]+)`/g, (_, code) =>
      `<code class="inline-code">${escapeHtml(code)}</code>`
    );
    // Bold
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Italic
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Newlines
    text = text.replace(/\n/g, '<br>');
    return text;
  }

  function escapeHtml(s: string): string {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
</script>

<div class="chat-messages" bind:this={chatContainer}>
  {#each messages as msg, i (msg.id)}
    <div class="msg-wrap" class:user={msg.sender === 'user'} style="animation-delay: {i * 0.05}s">
      <!-- Avatar -->
      {#if msg.sender === 'luna'}
        <div class="msg-avatar luna-av">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2a7 7 0 0 0 0 14 7 7 0 0 0 0-14"/>
          </svg>
        </div>
      {:else}
        <div class="msg-avatar user-av">P</div>
      {/if}

      <!-- Bubble -->
      <div class="msg-outer">
        <div class="msg" class:luna={msg.sender === 'luna'} class:user-msg={msg.sender === 'user'}>
          <div class="msg-text">{@html renderMarkdown(msg.text)}</div>
          <div class="meta">{formatTime(msg.timestamp)}</div>
        </div>
        {#if msg.sender === 'luna'}
          <button
            class="copy-btn speak-btn"
            class:speaking={speakingId === msg.id}
            onclick={() => { speakingId = msg.id; onSpeak?.(msg.text); setTimeout(() => { if (speakingId === msg.id) speakingId = null; }, 2000); }}
            title="Falar"
          >
            {#if speakingId === msg.id}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
            {:else}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
            {/if}
          </button>
        {/if}
        <button
          class="copy-btn"
          class:copied={copiedId === msg.id}
          onclick={() => copyMessage(msg.id, msg.text)}
          title="Copiar"
        >
          {#if copiedId === msg.id}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          {:else}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          {/if}
        </button>
      </div>
    </div>
  {/each}

  <!-- Typing indicator -->
  {#if isTyping}
    <div class="msg-wrap typing-wrap">
      <div class="msg-avatar luna-av">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
        </svg>
      </div>
      <div class="typing-indicator">
        <span class="tdot"></span>
        <span class="tdot"></span>
        <span class="tdot"></span>
        {#if currentAction}
          <span class="action-label">{currentAction}</span>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;
  }

  .msg-wrap {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    animation: msgIn 0.3s cubic-bezier(0.2, 1, 0.4, 1) both;
  }

  .msg-wrap.user { flex-direction: row-reverse; }

  .msg-avatar {
    width: 28px;
    height: 28px;
    border-radius: 10px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    align-self: flex-end;
  }

  .luna-av {
    background: rgba(59,158,255,0.15);
    border: 1px solid rgba(59,158,255,0.2);
    color: #3b9eff;
  }

  .user-av {
    background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
    color: white;
    border: none;
    box-shadow: 0 4px 10px rgba(0,0,0,0.2);
  }

  /* Outer wrapper for bubble + copy btn */
  .msg-outer {
    display: flex;
    align-items: flex-end;
    gap: 6px;
    max-width: calc(100% - 44px);
  }

  .msg-wrap.user .msg-outer { flex-direction: row-reverse; }

  .msg {
    flex: 1;
    padding: 12px 18px;
    line-height: 1.65;
    font-size: 13px;
    word-break: break-word;
    box-shadow: 0 8px 24px rgba(0,0,0,0.15);
  }

  .msg.luna {
    background: rgba(18, 18, 34, 0.7);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 20px 20px 20px 6px;
    backdrop-filter: blur(10px);
  }

  .msg.user-msg {
    background: linear-gradient(135deg, rgba(59,158,255,0.2), rgba(139,92,246,0.15));
    border: 1px solid rgba(59,158,255,0.3);
    border-radius: 20px 20px 6px 20px;
    backdrop-filter: blur(10px);
  }

  .msg-text { white-space: pre-wrap; }

  /* Markdown styles */
  .msg-text :global(strong) { font-weight: 600; color: rgba(255,255,255,0.9); }
  .msg-text :global(em) { font-style: italic; color: rgba(255,255,255,0.7); }
  .msg-text :global(.inline-code) {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    background: rgba(59,158,255,0.12);
    border: 1px solid rgba(59,158,255,0.2);
    border-radius: 4px;
    padding: 1px 6px;
    color: #6ec6ff;
  }
  .msg-text :global(.code-block) {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    background: rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 12px 14px;
    margin: 8px 0;
    overflow-x: auto;
    white-space: pre;
    color: #a5f3fc;
    line-height: 1.5;
  }

  .meta {
    font-size: 10px;
    color: rgba(255,255,255,0.2);
    margin-top: 6px;
    font-family: 'JetBrains Mono', monospace;
  }

  /* Copy button */
  .copy-btn {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s;
    flex-shrink: 0;
    margin-bottom: 28px;
  }

  .msg-wrap:hover .copy-btn { opacity: 1; }

  .copy-btn:hover {
    background: rgba(59,158,255,0.1);
    border-color: rgba(59,158,255,0.2);
    color: #3b9eff;
  }

  .copy-btn.copied {
    opacity: 1;
    background: rgba(34,197,94,0.1);
    border-color: rgba(34,197,94,0.2);
    color: #22c55e;
  }

  .speak-btn.speaking {
    opacity: 1;
    background: rgba(59,158,255,0.15);
    border-color: rgba(59,158,255,0.3);
    color: #3b9eff;
  }

  /* Typing */
  .typing-wrap { animation: msgIn 0.3s ease-out; }

  .typing-indicator {
    padding: 14px 18px;
    border-radius: 20px 20px 20px 6px;
    background: rgba(18, 18, 34, 0.7);
    border: 1px solid rgba(255,255,255,0.05);
    backdrop-filter: blur(10px);
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
  }

  .action-label {
    margin-left: 6px;
    font-size: 0.82rem;
    color: rgba(110, 198, 255, 0.9);
    font-weight: 500;
  }

  .tdot {
    width: 6px;
    height: 6px;
    background: #6ec6ff;
    border-radius: 50%;
    animation: typingDot 1.4s infinite;
  }

  .tdot:nth-child(2) { animation-delay: 0.2s; }
  .tdot:nth-child(3) { animation-delay: 0.4s; }
</style>
