<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { useLuna } from '$lib/stores/luna.svelte';

  const luna = useLuna();
  let nowPlaying = $state('—');

  async function control(action: string, val = 10) {
    const res = await luna.mediaControl(action, String(val));
    if (res && res.result) {
      nowPlaying = res.result;
    }
  }

  async function loadNowPlaying() {
    const res = await luna.mediaControl('now_playing', '0');
    if (res && res.result) {
      nowPlaying = res.result;
    }
  }

  onMount(() => {
    loadNowPlaying();
    const interval = setInterval(loadNowPlaying, 5000);
    return () => clearInterval(interval);
  });
</script>

<div class="panel-view">
  <div class="panel-header">
    <Icon name="music-2" />
    <h2>Mídia</h2>
  </div>
  <div class="panel-body">
    <!-- Bloco 1: Reprodução -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="music-2" size="14" />
        <span>Reprodução</span>
      </div>
      <div class="card">
        <div class="now-playing">{nowPlaying}</div>
        <div class="media-controls">
          <button class="btn" onclick={() => control('prev')} title="Anterior">
            <Icon name="skip-back" />
          </button>
          <button class="btn primary" onclick={() => control('play_pause')} title="Play / Pause">
            <Icon name="play" /> Play / Pause
          </button>
          <button class="btn" onclick={() => control('next')} title="Próximo">
            <Icon name="skip-forward" />
          </button>
        </div>
        <div class="media-subcontrols">
          <button class="btn sm" onclick={() => control('stop')}>
            <Icon name="square" size="14" /> Stop
          </button>
          <button class="btn sm" onclick={() => control('mute')}>
            <Icon name="volume-x" size="14" /> Mute
          </button>
        </div>
      </div>
    </div>

    <!-- Bloco 2: Volume -->
    <div class="panel-section">
      <div class="section-title">
        <Icon name="volume-2" size="14" />
        <span>Volume</span>
      </div>
      <div class="card">
        <div class="volume-row">
          <button class="btn sm" onclick={() => control('volume_down', 10)}>
            <Icon name="minus" size="14" /> 10
          </button>
          <button class="btn sm" onclick={() => control('volume_down', 5)}>
            <Icon name="minus" size="14" /> 5
          </button>
          <button class="btn sm" onclick={() => control('volume_up', 5)}>
            <Icon name="plus" size="14" /> 5
          </button>
          <button class="btn sm" onclick={() => control('volume_up', 10)}>
            <Icon name="plus" size="14" /> 10
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

  .now-playing { font-size: 13px; color: rgba(255, 255, 255, 0.6); min-height: 20px; font-style: italic; text-align: center; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.02); }

  .media-controls { display: flex; gap: 8px; justify-content: center; }
  .media-subcontrols { display: flex; gap: 8px; }

  .btn { display: flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid rgba(255,255,255,0.06); border-radius: 12px; background: rgba(255,255,255,0.03); color: rgba(255,255,255,0.7); cursor: pointer; transition: all 0.2s; font-size: 13px; font-weight: 500; padding: 10px 16px; }
  .btn:hover { background: rgba(255,255,255,0.08); color: white; border-color: rgba(255,255,255,0.12); }
  .btn:active { transform: scale(0.97); }

  .btn.primary { background: linear-gradient(135deg, #3b9eff, #8b5cf6); border: none; color: white; font-weight: 600; box-shadow: 0 4px 12px rgba(59, 158, 255, 0.2); flex: 1.5; }
  .btn.primary:hover { box-shadow: 0 6px 16px rgba(59, 158, 255, 0.35); transform: translateY(-0.5px); }

  .btn.sm { padding: 8px 12px; font-size: 11px; flex: 1; border-radius: 10px; }

  .volume-row { display: flex; gap: 6px; }
</style>
