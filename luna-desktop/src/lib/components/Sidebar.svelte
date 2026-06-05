<script lang="ts">
  import Icon from './Icon.svelte';

  let { activeTab = $bindable('chat'), onTabChange } = $props<{
    activeTab: string;
    onTabChange?: (tab: string) => void;
  }>();

  function selectTab(id: string) {
    activeTab = id;
    onTabChange?.(id);
  }

  const tabs = [
    { id: 'chat', label: 'Chat', icon: 'message-circle' },
    { id: 'voice', label: 'Voz', icon: 'mic' },
    { id: 'media', label: 'Mídia', icon: 'music-2' },
    { id: 'system', label: 'Sistema', icon: 'activity' },
    { id: 'control', label: 'Controle', icon: 'home' },
    { id: 'wiki', label: 'Wiki', icon: 'book-open' },
  ];

  const specialTabs = [
    { id: 'coding', label: 'Coding', color: '#fd9644', icon: 'code-2' },
    { id: 'write', label: 'Write', color: '#00d9a3', icon: 'pen-tool' },
    { id: 'joy', label: 'Joy', color: '#fd79a8', icon: 'gamepad-2' },
  ];
</script>

<aside class="sidebar">
  <!-- Logo -->
  <div class="sidebar-logo">
    <img src="/logo.png" alt="Luna" class="mini-orb-logo" />
  </div>

  <!-- Main Nav -->
  <nav class="sidebar-nav">
    {#each tabs as tab}
      <button
        class="nav-item"
        class:active={activeTab === tab.id}
        onclick={() => selectTab(tab.id)}
        title={tab.label}
      >
        <Icon name={tab.icon} size="18" />
        <span class="nav-label">{tab.label}</span>
      </button>
    {/each}

    <div class="nav-sep"></div>

    {#each specialTabs as tab}
      <button
        class="nav-item special"
        class:active={activeTab === tab.id}
        onclick={() => selectTab(tab.id)}
        title={tab.label}
        style="--tab-color: {tab.color};"
      >
        <Icon name={tab.icon} size="18" />
        <span class="nav-label">{tab.label}</span>
      </button>
    {/each}
  </nav>

  <!-- Status -->
  <div class="sidebar-status">
    <div class="status-avatar">
      <img src="/logo.png" alt="Luna" class="status-orb-mini-img" />
      <span class="status-dot-online"></span>
    </div>
    <div class="status-info">
      <span class="status-name">Luna</span>
      <span class="status-state">Online</span>
    </div>
  </div>
</aside>

<style>
  .sidebar {
    width: 80px;
    height: 100vh;
    background: rgba(8, 10, 22, 0.95);
    border-right: 1px solid rgba(255,255,255,0.04);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 16px 0 12px;
    position: relative;
    z-index: 10;
    backdrop-filter: blur(20px);
  }

  .sidebar-logo {
    width: 42px;
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 24px;
    cursor: pointer;
  }

  .mini-orb-logo {
    width: 36px;
    height: 36px;
    object-fit: contain;
    border-radius: 50%;
    box-shadow: 0 0 12px rgba(59,158,255,0.25);
    transition: transform 0.3s ease;
  }

  .mini-orb-logo:hover {
    transform: scale(1.1);
  }

  .sidebar-nav {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    width: 100%;
    padding: 0 8px;
  }

  .sidebar-nav::-webkit-scrollbar { width: 0; }

  .nav-sep {
    width: 40px;
    height: 1px;
    background: rgba(255,255,255,0.06);
    margin: 6px 0;
    flex-shrink: 0;
  }

  .nav-item {
    width: 64px;
    height: 52px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    background: transparent;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    color: rgba(255,255,255,0.35);
    flex-shrink: 0;
  }

  .nav-item:hover {
    background: rgba(255,255,255,0.04);
    color: rgba(255,255,255,0.7);
  }

  /* Tooltip */
  .nav-item::after {
    content: attr(title);
    position: absolute;
    left: calc(100% + 12px);
    top: 50%;
    transform: translateY(-50%) translateX(-4px);
    background: rgba(15, 17, 30, 0.95);
    border: 1px solid rgba(255,255,255,0.08);
    color: rgba(255,255,255,0.8);
    font-size: 11px;
    font-weight: 500;
    padding: 5px 10px;
    border-radius: 8px;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s, transform 0.15s;
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    z-index: 100;
  }

  .nav-item:hover::after {
    opacity: 1;
    transform: translateY(-50%) translateX(0);
  }

  .nav-item.active {
    background: rgba(59,158,255,0.1);
    color: #3b9eff;
  }

  .nav-item.active::before {
    content: '';
    position: absolute;
    left: -8px;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 20px;
    background: linear-gradient(180deg, #3b9eff, #6ec6ff);
    border-radius: 0 3px 3px 0;
  }

  .nav-item.special {
    color: var(--tab-color, rgba(255,255,255,0.35));
    opacity: 0.6;
  }

  .nav-item.special:hover {
    opacity: 1;
  }

  .nav-item.special.active {
    opacity: 1;
    background: color-mix(in srgb, var(--tab-color) 12%, transparent);
  }

  .nav-item.special.active::before {
    background: var(--tab-color);
  }

  .nav-label {
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.02em;
    line-height: 1;
  }

  .sidebar-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding-top: 12px;
    border-top: 1px solid rgba(255,255,255,0.04);
    width: 64px;
  }

  .status-avatar {
    position: relative;
    width: 28px;
    height: 28px;
  }

  .status-orb-mini-img {
    width: 28px;
    height: 28px;
    object-fit: contain;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(59,158,255,0.2);
  }

  .status-dot-online {
    position: absolute;
    bottom: -1px;
    right: -2px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #22c55e;
    border: 2px solid rgba(8, 10, 22, 0.95);
    animation: statusDot 2s ease-in-out infinite;
  }

  .status-info {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
  }

  .status-name {
    font-size: 9px;
    font-weight: 600;
    color: rgba(255,255,255,0.6);
  }

  .status-state {
    font-size: 7.5px;
    font-weight: 500;
    color: #22c55e;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
</style>
