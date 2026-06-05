<script lang="ts">
  import { onMount } from 'svelte';
  let canvas: HTMLCanvasElement;

  onMount(() => {
    const ctx = canvas.getContext('2d')!;
    let W = canvas.width  = canvas.offsetWidth;
    let H = canvas.height = canvas.offsetHeight;
    let raf: number;

    // ── Static stars ──────────────────────────────────────────
    interface Star { x: number; y: number; r: number; a: number; twinkleSpeed: number; twinklePhase: number; }
    const stars: Star[] = Array.from({ length: 180 }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.2 + 0.2,
      a: Math.random() * 0.6 + 0.15,
      twinkleSpeed: Math.random() * 0.02 + 0.005,
      twinklePhase: Math.random() * Math.PI * 2,
    }));

    // ── Shooting stars ────────────────────────────────────────
    interface Shoot {
      x: number; y: number;
      vx: number; vy: number;
      len: number; life: number; maxLife: number;
      width: number;
    }
    const shoots: Shoot[] = [];
    let nextShoot = 0;

    function spawnShoot() {
      const angle = (Math.random() * 30 + 15) * (Math.PI / 180); // 15–45°
      const speed = Math.random() * 6 + 5;
      shoots.push({
        x: Math.random() * W * 0.8,
        y: Math.random() * H * 0.4,
        vx:  Math.cos(angle) * speed,
        vy:  Math.sin(angle) * speed,
        len: Math.random() * 120 + 60,
        life: 0,
        maxLife: Math.random() * 60 + 40,
        width: Math.random() * 1.2 + 0.4,
      });
    }

    let t = 0;
    function tick() {
      ctx.clearRect(0, 0, W, H);
      t++;

      // Draw static stars
      for (const s of stars) {
        s.twinklePhase += s.twinkleSpeed;
        const alpha = s.a * (0.6 + 0.4 * Math.sin(s.twinklePhase));
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(200,220,255,${alpha})`;
        ctx.fill();
        // tiny glow on bigger stars
        if (s.r > 0.9) {
          const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 4);
          g.addColorStop(0, `rgba(180,210,255,${alpha * 0.4})`);
          g.addColorStop(1, 'rgba(180,210,255,0)');
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(s.x, s.y, s.r * 4, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Spawn shooting stars
      if (t >= nextShoot) {
        spawnShoot();
        nextShoot = t + Math.floor(Math.random() * 220 + 80);
      }

      // Draw & update shooting stars
      for (let i = shoots.length - 1; i >= 0; i--) {
        const s = shoots[i];
        const progress = s.life / s.maxLife;
        const alpha = progress < 0.2
          ? progress / 0.2
          : progress > 0.7
            ? 1 - (progress - 0.7) / 0.3
            : 1;

        const tailX = s.x - s.vx * (s.len / (s.vx ** 2 + s.vy ** 2) ** 0.5);
        const tailY = s.y - s.vy * (s.len / (s.vx ** 2 + s.vy ** 2) ** 0.5);

        const grad = ctx.createLinearGradient(tailX, tailY, s.x, s.y);
        grad.addColorStop(0, 'rgba(200,230,255,0)');
        grad.addColorStop(0.6, `rgba(200,230,255,${alpha * 0.4})`);
        grad.addColorStop(1, `rgba(255,255,255,${alpha})`);

        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(s.x, s.y);
        ctx.strokeStyle = grad;
        ctx.lineWidth = s.width * alpha;
        ctx.lineCap = 'round';
        ctx.stroke();

        // head glow
        const hg = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, 4);
        hg.addColorStop(0, `rgba(255,255,255,${alpha * 0.9})`);
        hg.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = hg;
        ctx.beginPath();
        ctx.arc(s.x, s.y, 4, 0, Math.PI * 2);
        ctx.fill();

        s.x += s.vx;
        s.y += s.vy;
        s.life++;
        if (s.life >= s.maxLife || s.x > W || s.y > H) shoots.splice(i, 1);
      }

      raf = requestAnimationFrame(tick);
    }

    const ro = new ResizeObserver(() => {
      W = canvas.width  = canvas.offsetWidth;
      H = canvas.height = canvas.offsetHeight;
      for (const s of stars) { s.x = Math.random() * W; s.y = Math.random() * H; }
    });
    ro.observe(canvas);

    tick();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); };
  });
</script>

<canvas bind:this={canvas} class="starfield"></canvas>

<style>
  .starfield {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 0;
  }
</style>
