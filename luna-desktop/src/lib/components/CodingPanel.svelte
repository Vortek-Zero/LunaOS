<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();

  let codeMessages = $state<Array<{ sender: 'sys' | 'user' | 'luna'; text: string }>>([
    { sender: 'sys', text: 'Luna Coder pronta. Descreva o que quer criar ou cole um erro para corrigir.' }
  ]);
  let codeInputText = $state('');
  let currentCode = $state('\x3c!DOCTYPE html\x3e\n\x3chtml\x3e\n\x3chead\x3e\n  \x3cstyle\x3e\n    body { background: #0b0c16; color: #a78bfa; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; }\n    h1 { border: 1px solid rgba(167,139,250,0.3); padding: 20px; border-radius: 12px; box-shadow: 0 0 20px rgba(167,139,250,0.1); }\n  \x3c/style\x3e\n\x3c/head\x3e\n\x3cbody\x3e\n  \x3ch1\x3eOlá da LUNA!\x3c/h1\x3e\n\x3c/body\x3e\n\x3c/html\x3e');
  let isCodingTyping = $state(false);
  let previewIframe: HTMLIFrameElement;

  function updatePreview() {
    if (previewIframe) {
      const doc = previewIframe.contentDocument || previewIframe.contentWindow?.document;
      if (doc) {
        doc.open();
        doc.write(currentCode);
        doc.close();
      }
    }
  }

  async function sendCodeMessage() {
    if (!codeInputText.trim()) return;
    const msg = codeInputText.trim();
    codeMessages.push({ sender: 'user', text: msg });
    codeInputText = '';
    isCodingTyping = true;

    const res = await luna.sendCodeChat(msg, currentCode, 'default');
    isCodingTyping = false;

    if (res) {
      if (res.code) {
        currentCode = res.code;
        updatePreview();
      }
      if (res.explanation) {
        codeMessages.push({ sender: 'luna', text: res.explanation });
      }
    } else {
      codeMessages.push({ sender: 'luna', text: '⚠️ Falha ao se conectar com o módulo de código.' });
    }
  }

  function downloadCode() {
    const blob = new Blob([currentCode], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'luna_app.html';
    a.click();
    URL.revokeObjectURL(url);
  }

  function copyCode() {
    navigator.clipboard.writeText(currentCode);
    alert('Código copiado para a área de transferência!');
  }

  async function clearSession() {
    if (!confirm('Deseja limpar o histórico da conversa de código?')) return;
    await luna.clearCodeSession('default');
    codeMessages = [{ sender: 'sys', text: 'Sessão reiniciada. Luna Coder pronta.' }];
  }

  onMount(() => {
    updatePreview();
  });
</script>

<div class="coding-layout">
  <!-- Col 1: Chat -->
  <div class="code-col">
    <div class="code-col-head">
      <Icon name="message-circle" size="14" />
      <span>Chat do Programador</span>
      <button class="icon-btn" onclick={clearSession} title="Limpar conversa">
        <Icon name="trash-2" size="14" />
      </button>
    </div>
    <div class="code-chat-messages">
      {#each codeMessages as msg}
        <div class="cmsg" class:sys={msg.sender === 'sys'} class:user={msg.sender === 'user'} class:luna={msg.sender === 'luna'}>
          <div class="cmsg-text">{msg.text}</div>
        </div>
      {/each}
      {#if isCodingTyping}
        <div class="cmsg coding-typing">
          <div class="tdot"></div>
          <div class="tdot"></div>
          <div class="tdot"></div>
        </div>
      {/if}
    </div>
    <div class="code-chat-input-row">
      <textarea
        bind:value={codeInputText}
        placeholder="Descreva o que quer criar..."
        onkeydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendCodeMessage(); } }}
      ></textarea>
      <button onclick={sendCodeMessage} class="btn-send">
        <Icon name="plus" size="14" />
      </button>
    </div>
  </div>

  <!-- Col 2: Editor -->
  <div class="code-col">
    <div class="code-col-head">
      <Icon name="code-2" size="14" />
      <span>Editor de Código</span>
      <div class="actions">
        <button class="btn sm" onclick={downloadCode}>
          <Icon name="minus" size="12" /> .html
        </button>
        <button class="icon-btn" onclick={copyCode} title="Copiar código">
          <Icon name="refresh-cw" size="14" />
        </button>
      </div>
    </div>
    <textarea
      class="code-editor"
      spellcheck="false"
      bind:value={currentCode}
      oninput={updatePreview}
      placeholder="O código gerado aparecerá aqui..."
    ></textarea>
  </div>

  <!-- Col 3: Preview -->
  <div class="code-col">
    <div class="code-col-head">
      <Icon name="activity" size="14" />
      <span>Visualização ao Vivo</span>
      <button class="icon-btn" onclick={updatePreview} title="Atualizar visualização">
        <Icon name="refresh-cw" size="14" />
      </button>
    </div>
    <div class="preview-container">
      <iframe
        bind:this={previewIframe}
        title="Visualização do código gerado"
        sandbox="allow-scripts allow-same-origin allow-forms allow-modals"
      ></iframe>
    </div>
  </div>
</div>

<style>
  .coding-layout { display: flex; width: 100%; height: 100%; overflow: hidden; background: rgba(5, 6, 12, 0.4); }

  .code-col { flex: 1; display: flex; flex-direction: column; border-right: 1px solid rgba(255,255,255,0.04); background: rgba(10, 11, 20, 0.4); overflow: hidden; min-width: 0; }
  .code-col:last-child { border-right: none; }

  .code-col-head { height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-bottom: 1px solid rgba(255,255,255,0.04); background: rgba(0,0,0,0.15); font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.6); }
  .code-col-head span { margin-left: 6px; flex: 1; }
  .code-col-head :global(svg) { color: #fd9644; }

  .actions { display: flex; align-items: center; gap: 6px; }

  .icon-btn { background: transparent; border: none; color: rgba(255,255,255,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 6px; transition: all 0.2s; }
  .icon-btn:hover { background: rgba(255,255,255,0.04); color: white; }

  .btn { display: flex; align-items: center; justify-content: center; gap: 6px; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.7); cursor: pointer; transition: all 0.2s; font-size: 11px; padding: 4px 8px; }
  .btn:hover { background: rgba(255,255,255,0.05); color: white; }
  .btn.sm { font-size: 10px; padding: 3px 6px; }

  /* Chat list */
  .code-chat-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
  
  .cmsg { padding: 10px 14px; border-radius: 12px; font-size: 12.5px; line-height: 1.5; max-width: 90%; word-break: break-word; white-space: pre-wrap; overflow-wrap: anywhere; }
  .cmsg.sys { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); color: rgba(255,255,255,0.4); max-width: 100%; font-style: italic; }
  .cmsg.user { background: rgba(253, 150, 68, 0.1); border: 1px solid rgba(253, 150, 68, 0.25); color: white; align-self: flex-end; border-bottom-right-radius: 3px; }
  .cmsg.luna { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); color: rgba(255,255,255,0.85); align-self: flex-start; border-bottom-left-radius: 3px; }
  .cmsg-text { white-space: pre-wrap; overflow-wrap: anywhere; }

  .coding-typing { display: flex; gap: 4px; align-items: center; background: rgba(255,255,255,0.02); border: none; align-self: flex-start; padding: 8px 12px; }
  .tdot { width: 4px; height: 4px; background: #fd9644; border-radius: 50%; animation: typingDot 1.4s infinite; }
  .tdot:nth-child(2) { animation-delay: 0.2s; }
  .tdot:nth-child(3) { animation-delay: 0.4s; }

  .code-chat-input-row { display: flex; gap: 6px; padding: 10px; border-top: 1px solid rgba(255,255,255,0.04); background: rgba(0,0,0,0.1); }
  .code-chat-input-row textarea { flex: 1; height: 38px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: white; font-size: 12.5px; padding: 8px 10px; resize: none; outline: none; }
  .code-chat-input-row textarea:focus { border-color: rgba(253, 150, 68, 0.3); }

  .btn-send { width: 38px; height: 38px; border: none; border-radius: 8px; background: linear-gradient(135deg, #fd9644, #fa8231); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .btn-send:hover { transform: scale(1.02); }

  /* Editor */
  .code-editor { flex: 1; border: none; background: rgba(5, 6, 12, 0.95); color: #c5c6d0; font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 16px; outline: none; resize: none; line-height: 1.6; }
  .code-editor::placeholder { color: rgba(255,255,255,0.15); }

  /* Preview */
  .preview-container { flex: 1; background: white; position: relative; }
  .preview-container iframe { width: 100%; height: 100%; border: none; background: white; }
</style>
