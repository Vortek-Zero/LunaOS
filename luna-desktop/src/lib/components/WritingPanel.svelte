<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();

  let projects = $state<any[]>([]);
  let activeProjectId = $state('');
  let activeProject = $state<any>(null);

  let editorText = $state('');
  let activeStyle = $state('neutro');
  let writePhase = $state('Pronto');
  let isWriting = $state(false);

  let chatMessages = $state<Array<{ sender: 'sys' | 'user' | 'luna'; text: string }>>([
    { sender: 'sys', text: 'Luna Write ativa. Descreva o que você quer escrever e eu gerarei em tempo real.' }
  ]);
  let chatInputText = $state('');

  // Modal states
  let showNewProjectModal = $state(false);
  let newProjectTitle = $state('');
  let newProjectGenre = $state('ficção');

  async function loadProjects() {
    const res = await luna.fetchWriteProjects();
    if (res && res.projects) {
      projects = res.projects;
      if (projects.length > 0 && !activeProjectId) {
        selectProject(projects[0].project_id);
      }
    }
  }

  async function selectProject(id: string) {
    activeProjectId = id;
    const res = await luna.getWriteProject(id);
    if (res) {
      activeProject = { ...res, id: res.project_id };
      editorText = res.text || '';
      activeStyle = res.style || 'neutro';
    }
  }

  async function createProject() {
    if (!newProjectTitle.trim()) return;
    const res = await luna.createWriteProject(newProjectTitle.trim(), newProjectGenre, activeStyle, []);
    if (res && res.project) {
      showNewProjectModal = false;
      newProjectTitle = '';
      await loadProjects();
      selectProject(res.project.project_id);
    }
  }

  async function saveText() {
    if (!activeProjectId) return;
    await luna.updateWriteProjectText(activeProjectId, editorText);
    alert('História salva com sucesso!');
  }

  async function deleteProject(id: string) {
    if (!confirm('Deseja excluir este projeto permanentemente?')) return;
    await luna.deleteWriteProject(id);
    if (activeProjectId === id) {
      activeProjectId = '';
      activeProject = null;
      editorText = '';
    }
    await loadProjects();
  }

  async function startAIGeneration() {
    if (!chatInputText.trim()) return;
    const prompt = chatInputText.trim();
    chatMessages.push({ sender: 'user', text: prompt });
    chatInputText = '';
    isWriting = true;
    writePhase = 'Planejando...';

    if (!activeProjectId) {
      chatMessages.push({ sender: 'luna', text: '✍️ Pensando...' });
      try {
        const resp = await luna.sendWriteChat(prompt, editorText);
        chatMessages.pop();
        if (resp?.response) {
          chatMessages.push({ sender: 'luna', text: resp.response });
        }
      } catch (e: any) {
        chatMessages.pop();
        chatMessages.push({ sender: 'luna', text: `⚠️ Erro: ${e.message || e}` });
      }
      isWriting = false;
      writePhase = 'Pronto';
      return;
    }

    editorText += '\n\n';

    await luna.streamWrite(
      {
        prompt,
        project_id: activeProjectId,
        style: activeStyle,
        chapter: activeProject?.chapters?.length || 0
      },
      (chunk) => {
        editorText += chunk;
      },
      (phase) => {
        if (phase === 'planning_done') {
          writePhase = 'Escrevendo...';
        }
      },
      async () => {
        isWriting = false;
        writePhase = 'Pronto';
        chatMessages.push({ sender: 'luna', text: 'Capítulo gerado e adicionado ao editor.' });
        await luna.updateWriteProjectText(activeProjectId, editorText);
      },
      (err) => {
        isWriting = false;
        writePhase = 'Erro';
        chatMessages.push({ sender: 'luna', text: `⚠️ Erro: ${err}` });
      }
    );
  }

  function exportTxt() {
    const blob = new Blob([editorText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeProject?.title || 'historia'}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function addChapter() {
    if (!activeProjectId) return;
    const title = prompt('Título do capítulo:');
    if (title === null) return;
    await luna.addWriteChapter(activeProjectId, title);
    await selectProject(activeProjectId);
  }

  let wordCount = $derived(editorText ? editorText.trim().split(/\s+/).filter(Boolean).length : 0);
  let chapterCount = $derived(activeProject?.chapters?.length || 0);

  onMount(() => {
    loadProjects();
  });
</script>

<div class="write-layout">
  <!-- Col 1: Projects Sidebar -->
  <div class="write-col sidebar-col">
    <div class="write-col-head">
      <Icon name="book-open" size="14" />
      <span>Projetos</span>
    </div>
    <div class="projects-list">
      {#each projects as p}
        <div class="project-item" class:active={p.project_id === activeProjectId}>
          <button class="project-btn" onclick={() => selectProject(p.project_id)}>
            <span class="p-title">{p.title}</span>
            <span class="p-genre">{p.genre}</span>
          </button>
          <button class="delete-btn" onclick={() => deleteProject(p.project_id)}>✕</button>
        </div>
      {/each}
    </div>
    <button class="new-project-btn" onclick={() => showNewProjectModal = true}>
      <Icon name="plus" size="12" /> Novo Projeto
    </button>
  </div>

  <!-- Col 2: Text Editor -->
  <div class="write-col editor-col">
    <div class="write-col-head">
      <Icon name="pen-tool" size="14" />
      <span>Editor Criativo</span>
      <div class="actions">
        <button class="btn sm" onclick={addChapter}>+ Cap</button>
        <button class="btn sm" onclick={saveText} title="Salvar">
          <Icon name="plus" size="12" /> Salvar
        </button>
        <button class="icon-btn" onclick={exportTxt} title="Exportar .txt">
          <Icon name="refresh-cw" size="14" />
        </button>
      </div>
    </div>

    <!-- Style Bar -->
    <div class="style-bar">
      {#each ['neutro', 'adolescente', 'adulto', 'thriller', 'romance', 'infantil'] as style}
        <button
          class="style-btn"
          class:active={activeStyle === style}
          onclick={() => activeStyle = style}
        >
          {style.charAt(0).toUpperCase() + style.slice(1)}
        </button>
      {/each}
    </div>

    <textarea
      class="write-textarea"
      bind:value={editorText}
      placeholder="Escreva aqui ou converse com a Luna Write ao lado para gerar o texto..."
    ></textarea>

    <div class="status-bar">
      <div class="phase-indicator">
        <span class="dot" class:active={isWriting}></span>
        <span>{writePhase}</span>
      </div>
      <div class="counters">
        <span>{wordCount} palavras</span>
        <span>{chapterCount} capítulos</span>
      </div>
    </div>
  </div>

  <!-- Col 3: Write Chat -->
  <div class="write-col chat-col">
    <div class="write-col-head">
      <Icon name="message-circle" size="14" />
      <span>Chat do Escritor</span>
    </div>
    <div class="write-chat-messages">
      {#each chatMessages as msg}
        <div class="wmsg" class:sys={msg.sender === 'sys'} class:user={msg.sender === 'user'} class:luna={msg.sender === 'luna'}>
          <div class="wmsg-text">{msg.text}</div>
        </div>
      {/each}
      {#if isWriting}
        <div class="wmsg writing-indicator">
          <span class="wdot"></span>
          <span class="wdot"></span>
          <span class="wdot"></span>
        </div>
      {/if}
    </div>
    <div class="write-chat-input-row">
      <textarea
        bind:value={chatInputText}
        placeholder="Escreva o próximo capítulo..."
        onkeydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startAIGeneration(); } }}
      ></textarea>
      <button onclick={startAIGeneration} class="btn-send" disabled={isWriting}>
        <Icon name="plus" size="14" />
      </button>
    </div>
  </div>
</div>

<!-- Modal -->
{#if showNewProjectModal}
  <div class="modal-overlay">
    <div class="modal">
      <h3>Novo Projeto de Escrita</h3>
      <div class="form-group">
        <label for="newProjectTitle">Título</label>
        <input id="newProjectTitle" class="field" bind:value={newProjectTitle} placeholder="Nome do livro/projeto..." />
      </div>
      <div class="form-group">
        <label for="newProjectGenre">Gênero</label>
        <select id="newProjectGenre" class="field" bind:value={newProjectGenre}>
          <option value="ficção">Ficção Geral</option>
          <option value="fantasia">Fantasia / Sci-Fi</option>
          <option value="romance">Romance</option>
          <option value="thriller">Thriller / Mistério</option>
          <option value="infantil">Infantil</option>
        </select>
      </div>
      <div class="modal-buttons">
        <button class="btn" onclick={() => showNewProjectModal = false}>Cancelar</button>
        <button class="btn primary" onclick={createProject}>Criar</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .write-layout { display: flex; width: 100%; height: 100%; overflow: hidden; background: rgba(5, 6, 12, 0.4); }

  .write-col { display: flex; flex-direction: column; border-right: 1px solid rgba(255,255,255,0.04); background: rgba(10, 11, 20, 0.4); overflow: hidden; }
  .write-col:last-child { border-right: none; }

  .sidebar-col { width: 160px; flex-shrink: 0; }
  .editor-col { flex: 2; }
  .chat-col { flex: 1; }

  .write-col-head { height: 42px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-bottom: 1px solid rgba(255,255,255,0.04); background: rgba(0,0,0,0.15); font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.6); }
  .write-col-head span { margin-left: 6px; flex: 1; }
  .write-col-head :global(svg) { color: #00d9a3; }

  .actions { display: flex; align-items: center; gap: 6px; }

  .icon-btn { background: transparent; border: none; color: rgba(255,255,255,0.4); cursor: pointer; display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 6px; transition: all 0.2s; }
  .icon-btn:hover { background: rgba(255,255,255,0.04); color: white; }

  .btn { display: flex; align-items: center; justify-content: center; gap: 6px; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.7); cursor: pointer; transition: all 0.2s; font-size: 11px; padding: 4px 8px; }
  .btn:hover { background: rgba(255,255,255,0.05); color: white; }
  .btn.primary { background: linear-gradient(135deg, #00d9a3, #02b387); border: none; color: white; }
  .btn.sm { font-size: 10px; padding: 3px 6px; }

  /* Project items */
  .projects-list { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
  .project-item { display: flex; align-items: center; border-radius: 8px; border: 1px solid transparent; transition: all 0.2s; }
  .project-item:hover { background: rgba(255,255,255,0.02); }
  .project-item.active { background: rgba(0, 217, 163, 0.08); border-color: rgba(0, 217, 163, 0.2); }
  
  .project-btn { flex: 1; display: flex; flex-direction: column; text-align: left; background: transparent; border: none; padding: 8px 10px; cursor: pointer; overflow: hidden; }
  .p-title { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.85); white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }
  .p-genre { font-size: 9.5px; color: rgba(255,255,255,0.35); text-transform: uppercase; margin-top: 2px; }

  .delete-btn { background: transparent; border: none; color: rgba(255,255,255,0.25); cursor: pointer; padding: 8px; font-size: 11px; }
  .delete-btn:hover { color: #ef4444; }

  .new-project-btn { margin: 8px; padding: 8px; border-radius: 8px; border: 1px dashed rgba(0, 217, 163, 0.3); background: transparent; color: #00d9a3; font-size: 11px; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px; }
  .new-project-btn:hover { background: rgba(0, 217, 163, 0.05); }

  /* Style Bar */
  .style-bar { display: flex; gap: 4px; padding: 8px; background: rgba(0,0,0,0.1); border-bottom: 1px solid rgba(255,255,255,0.03); overflow-x: auto; }
  .style-btn { padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.04); background: rgba(255,255,255,0.02); color: rgba(255,255,255,0.45); font-size: 10.5px; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
  .style-btn:hover { color: white; }
  .style-btn.active { background: rgba(0, 217, 163, 0.15); border-color: rgba(0, 217, 163, 0.3); color: #00d9a3; font-weight: 600; }

  /* Textarea */
  .write-textarea { flex: 1; border: none; background: rgba(5, 6, 12, 0.95); color: #c5c6d0; font-family: 'Inter', sans-serif; font-size: 13.5px; padding: 20px; outline: none; resize: none; line-height: 1.85; word-spacing: 0.02em; }

  /* Status Bar */
  .status-bar { height: 28px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-top: 1px solid rgba(255,255,255,0.04); background: rgba(0,0,0,0.15); font-size: 10px; color: rgba(255,255,255,0.35); }
  .phase-indicator { display: flex; align-items: center; gap: 6px; }
  .phase-indicator .dot { width: 5px; height: 5px; background: rgba(255,255,255,0.15); border-radius: 50%; }
  .phase-indicator .dot.active { background: #00d9a3; animation: blink 1.2s infinite; }
  .counters { display: flex; gap: 12px; }

  /* Chat list */
  .write-chat-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
  .wmsg { padding: 10px 14px; border-radius: 12px; font-size: 12.5px; line-height: 1.5; max-width: 90%; word-break: break-word; }
  .wmsg.sys { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); color: rgba(255,255,255,0.4); max-width: 100%; font-style: italic; }
  .wmsg.user { background: rgba(0, 217, 163, 0.1); border: 1px solid rgba(0, 217, 163, 0.25); color: white; align-self: flex-end; border-bottom-right-radius: 3px; }
  .wmsg.luna { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); color: rgba(255,255,255,0.85); align-self: flex-start; border-bottom-left-radius: 3px; }

  .writing-indicator { display: flex; gap: 4px; align-items: center; background: rgba(255,255,255,0.02); border: none; align-self: flex-start; padding: 8px 12px; }
  .wdot { width: 4px; height: 4px; background: #00d9a3; border-radius: 50%; animation: typingDot 1.4s infinite; }
  .wdot:nth-child(2) { animation-delay: 0.2s; }
  .wdot:nth-child(3) { animation-delay: 0.4s; }

  .write-chat-input-row { display: flex; gap: 6px; padding: 10px; border-top: 1px solid rgba(255,255,255,0.04); background: rgba(0,0,0,0.1); }
  .write-chat-input-row textarea { flex: 1; height: 38px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; color: white; font-size: 12.5px; padding: 8px 10px; resize: none; outline: none; }
  .write-chat-input-row textarea:focus { border-color: rgba(0, 217, 163, 0.3); }

  .btn-send { width: 38px; height: 38px; border: none; border-radius: 8px; background: linear-gradient(135deg, #00d9a3, #02b387); color: white; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .btn-send:hover:not(:disabled) { transform: scale(1.02); }
  .btn-send:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Modal */
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 100; backdrop-filter: blur(4px); }
  .modal { background: #0f101d; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 24px; width: 320px; display: flex; flex-direction: column; gap: 16px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }
  .modal h3 { font-size: 15px; font-weight: 600; color: white; margin: 0; }
  .form-group { display: flex; flex-direction: column; gap: 6px; }
  .form-group label { font-size: 11px; color: rgba(255,255,255,0.4); font-weight: 600; text-transform: uppercase; }
  .modal-buttons { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

  .field { background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; color: white; font-size: 13px; padding: 10px 14px; outline: none; }
  .field:focus { border-color: rgba(0, 217, 163, 0.3); }

  @keyframes blink { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
</style>
