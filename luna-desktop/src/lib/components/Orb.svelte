<script lang="ts">
  import { onMount } from "svelte";

  let {
    status = "idle",
    audioLevel = 0,
    processingHeat = 0,  // 0-1: quão intenso é o processamento (tools/tokens)
    mini = false,
    speed = 1.0,
    intensity = 1.0,
  } = $props();

  let canvas: HTMLCanvasElement;
  let gl: WebGLRenderingContext | null = null;
  let program: WebGLProgram | null = null;
  let positionBuffer: WebGLBuffer | null = null;
  let animationFrameId: number;
  let startTime = Date.now();

  // Estados reativos
  let mouseX = $state(0);
  let mouseY = $state(0);
  let currentMouseX = $state(0);
  let currentMouseY = $state(0);
  let localAudio = $state(0);
  let audioBass = $state(0);
  let audioMid = $state(0);
  let audioTreble = $state(0);
  let breathPhase = $state(0);

  let scale = $derived(1 + localAudio * 0.22 * intensity);

  // Vertex Shader
  const vsSource = `
		attribute vec2 position;
		varying vec2 v_uv;
		void main() {
			v_uv = position * 0.5 + 0.5;
			v_uv.y = 1.0 - v_uv.y;
			gl_Position = vec4(position, 0.0, 1.0);
		}
	`;

  // Fragment Shader - Soothing Bluish Nebula with Twinkling Stars and CAVA-style Audio Visualizer
  const fsSource = `
		precision mediump float;
		uniform float u_time;
		uniform float u_audio;
		uniform float u_bass;
		uniform float u_mid;
		uniform float u_treble;
		uniform float u_heat;
		uniform vec2 u_mouse;
		varying vec2 v_uv;

		float hash(vec2 p) {
			return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
		}

		float noise(vec2 p) {
			vec2 i = floor(p);
			vec2 f = fract(p);
			f = f * f * (3.0 - 2.0 * f);
			return mix(mix(hash(i + vec2(0.0,0.0)), hash(i + vec2(1.0,0.0)), f.x),
					   mix(hash(i + vec2(0.0,1.0)), hash(i + vec2(1.0,1.0)), f.x), f.y);
		}

		float fbm(vec2 p, float t) {
			float v = 0.0;
			float a = 0.5;
			mat2 rot = mat2(0.87758, 0.47942, -0.47942, 0.87758);
			vec2 shift = vec2(100.0);
			for (int i = 0; i < 4; i++) {
				v += a * noise(p);
				p = rot * p * 2.02 + shift + t * 0.1;
				a *= 0.5;
			}
			return v;
		}

		// Procedural twinkling starfield using cell-based hashing
		float stars(vec2 uv, float scale, float t) {
			vec2 cell = floor(uv * scale);
			vec2 sub = fract(uv * scale);

			float rnd = hash(cell);
			vec2 starPos = vec2(hash(cell + vec2(1.0, 0.0)), hash(cell + vec2(0.0, 1.0)));

			float d = length(sub - starPos);

			float hasStar = step(0.78, rnd);
			float size = 0.015 + rnd * 0.025;

			float core = smoothstep(size, size * 0.15, d);
			float glow = smoothstep(size * 4.0, 0.0, d) * 0.25;

			float twinkleSpeed = 1.5 + rnd * 3.0;
			float twinklePhase = rnd * 6.28318;
			float twinkle = sin(t * twinkleSpeed + twinklePhase) * 0.5 + 0.5;
			twinkle = pow(twinkle, 1.5);

			return (core + glow) * hasStar * (0.3 + 0.7 * twinkle);
		}

		// ── CAVA-STYLE AUDIO VISUALIZER BANDS ──
		float cavaBands(vec2 uv, vec2 center, float t, float audio, float bass, float mid, float treble) {
			float bandCount = 24.0;
			float angle = atan(uv.y - center.y, uv.x - center.x);
			float normAngle = (angle / 6.28318) + 0.5;
			if (normAngle > 1.0) normAngle -= 1.0;

			float band = floor(normAngle * bandCount);
			float bandFrac = fract(normAngle * bandCount);

			// Map bands: low angles = bass, mid angles = mid, high angles = treble
			float bandRatio = band / bandCount;
			float bassWeight = 1.0 - smoothstep(0.0, 0.4, bandRatio);
			float midWeight = 1.0 - abs(bandRatio - 0.5) * 2.0;
			float trebleWeight = 1.0 - smoothstep(0.6, 1.0, 1.0 - bandRatio);

			float bandEnergy = bass * bassWeight + mid * midWeight + treble * trebleWeight;
			bandEnergy = clamp(bandEnergy, 0.0, 1.0);

			// Procedural variation per band for organic look
			float freqPhase = band / bandCount;
			float variation = 0.3 + 0.5 * sin(t * 3.0 + freqPhase * 12.56)
					+ 0.3 * sin(t * 5.1 + freqPhase * 8.3)
					+ 0.2 * sin(t * 7.7 + freqPhase * 15.1);
			float bandMag = bandEnergy * max(0.2, 0.5 + 0.5 * variation);
			bandMag = clamp(bandMag, 0.0, 1.0);
			bandMag = pow(bandMag, 1.6); // contrast boost

			// Falloff from center — bars grow outward with audio
			float distFromCenter = length(uv - center);
			float bandHeight = 0.02 + bandMag * 0.40;

			float glow = smoothstep(distFromCenter, distFromCenter - bandHeight, 0.5);
			// Soft edges between bands
			float edgeFade = 1.0 - smoothstep(0.0, 0.08, abs(bandFrac - 0.5));
			float bandGlow = glow * (0.3 + 0.7 * edgeFade);

			// Extra flash at peak
			float peakFlash = smoothstep(0.75, 0.95, bandMag) * bandMag * 0.6;

			return (bandGlow + peakFlash) * audio;
		}

		// ── AUDIO RING PULSES ──
		float audioRings(vec2 uv, vec2 center, float t, float audio) {
			float dist = length(uv - center);
			float rings = 0.0;

			// Three concentric rings expanding at different speeds
			for (int i = 0; i < 3; i++) {
				float fi = float(i);
				float speed = 1.2 + fi * 0.7;
				float phase = t * speed + fi * 1.5;
				float ringPos = 0.15 + 0.35 * (0.5 + 0.5 * sin(phase));
				float ringWidth = 0.015 + audio * 0.04;
				float ring = smoothstep(ringPos + ringWidth, ringPos, abs(dist - ringPos));
				ring *= 0.3 + 0.7 * (0.5 + 0.5 * sin(phase + 1.57));
				ring *= 0.3 + 0.7 * audio;
				rings += ring;
			}
			return rings;
		}

		// ── AUDIO WAVES (distortion on the nebula) ──
		float audioWaves(vec2 uv, float t, float audio) {
			float wave = 0.0;
			for (int i = 0; i < 3; i++) {
				float fi = float(i);
				float freq = 4.0 + fi * 3.0;
				float speed = 2.0 + fi * 1.3;
				float y = uv.y + 0.3 * sin(uv.x * freq + t * speed);
				float band = 1.0 - abs(y * 2.0 - 1.0);
				band = pow(band, 3.0);
				// Each band gets stronger with audio
				float bandAudio = audio * (0.5 + 0.5 * sin(t * 1.7 + fi * 2.1));
				wave += band * bandAudio * 0.25;
			}
			return wave;
		}

		void main() {
			vec2 uv = v_uv;
			vec2 center = vec2(0.5);
			float dist = length(uv - center);
			float alpha = smoothstep(0.5, 0.482, dist);
			if (alpha <= 0.0) discard;

			// Audio-normalized: smooth breathing when idle, pulsing when active
			float audio = u_audio;

			vec2 p = uv * 3.6 - u_mouse * 0.22;
			float t = u_time * 0.12 * 1.5;

			// ── 1. NEBULA CORE ──
			// Audio waves distort the nebula coordinates
			float waveDistort = audioWaves(uv, t, audio);
			vec2 audioP = p + vec2(waveDistort * 0.5, waveDistort * 0.3);

			vec2 q = vec2(
				fbm(audioP + vec2(0.0, 0.0) + t * 0.6, t),
				fbm(audioP + vec2(5.2, 1.8) + t * 0.9, t)
			);
			float f = fbm(audioP + 3.0 * q + t * 0.4, t);

			// Bluish, calming celestial colors
			vec3 indigo       = vec3(0.02, 0.04, 0.12);
			vec3 softBlue     = vec3(0.24, 0.58, 0.95);
			vec3 softCyan     = vec3(0.36, 0.82, 0.98);
			vec3 lavenderBlue = vec3(0.58, 0.62, 0.94);
			vec3 pearlWhite   = vec3(0.96, 0.98, 1.0);
			vec3 hotPink      = vec3(0.95, 0.30, 0.65);

			// Volumetric Fluid Nebula
			float shimmer = sin(f * 10.0 + t * 1.5) * 0.5 + 0.5;
			vec3 color = mix(indigo, lavenderBlue, f * 1.1);
			color = mix(color, softBlue, shimmer * 0.75);
			color = mix(color, softCyan, pow(shimmer, 2.0) * 0.65);

			// Audio drives color toward pearl white / hot pink at peak
			float colorPulse = 0.45 + audio * 0.95;
			color = mix(color, pearlWhite, pow(shimmer, 3.2) * colorPulse);

			// Processing heat — brighter / warmer with more tools/tokens
			float heat = u_heat;
			color = mix(color, pearlWhite, heat * 0.3);
			color = mix(color, hotPink, heat * 0.1);

			// Subtle warm shift on high audio
			vec3 warmGlow = mix(pearlWhite, hotPink, 0.3);
			color = mix(color, warmGlow, audio * 0.15);

			// ── 2. TWINKLING STARS ──
			float s1 = stars(uv + u_mouse * 0.03, 12.0, u_time);
			float s2 = stars(uv + u_mouse * 0.05 + vec2(0.33, 0.77), 18.0, u_time);
			float s3 = stars(uv + u_mouse * 0.08 + vec2(0.61, 0.19), 28.0, u_time);

			float starBoost = 1.0 + audio * 2.0;

			float nebulaLuminance = dot(color, vec3(0.299, 0.587, 0.114));
			float starVisibility = 1.0 - smoothstep(0.15, 0.55, nebulaLuminance);

			vec3 starColor1 = softCyan * s1 * 1.2;
			vec3 starColor2 = pearlWhite * s2 * 1.0;
			vec3 starColor3 = lavenderBlue * s3 * 0.7;

			color += (starColor1 + starColor2 + starColor3) * starBoost * (0.4 + starVisibility * 0.6);

			// ── 3. CAVA-STYLE AUDIO BANDS ──
			float cava = cavaBands(uv, center, t, audio, u_bass, u_mid, u_treble);
			color += vec3(0.2, 0.5, 0.9) * cava * 0.6;
			color += vec3(0.6, 0.8, 1.0) * cava * cava * 0.4;

			// ── 4. AUDIO RINGS ──
			float rings = audioRings(uv, center, t, audio);
			color += vec3(0.3, 0.7, 1.0) * rings * 0.5;

			// ── 5. SPECULAR + RIM ──
			float specular = pow(1.0 - dist * 1.8, 6.0) * 0.62;
			color += specular * vec3(0.92, 0.96, 1.0);

			float rim = smoothstep(0.45, 0.5, dist);
			color += rim * mix(softCyan, hotPink, heat * 0.5) * (0.55 + audio * 0.4 + heat * 0.3);

			// Audio + heat energy boost
			color = mix(color, pearlWhite, audio * 0.2 + heat * 0.1);

			// Alpha slightly brighter with audio
			float finalAlpha = alpha * (0.96 + audio * 0.04);

			gl_FragColor = vec4(color, finalAlpha);
		}
	`;

  function createShader(
    gl: WebGLRenderingContext,
    type: number,
    source: string,
  ): WebGLShader | null {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error("Shader compile error:", gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  function handleMouseMove(e: MouseEvent) {
    if (mini) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    mouseX = (e.clientX - rect.left) / rect.width - 0.5;
    mouseY = (e.clientY - rect.top) / rect.height - 0.5;
  }

  function handleMouseLeave() {
    mouseX = 0;
    mouseY = 0;
  }

  onMount(() => {
    gl =
      canvas.getContext("webgl", { alpha: true, premultipliedAlpha: false }) ||
      (canvas.getContext("experimental-webgl", {
        alpha: true,
        premultipliedAlpha: false,
      }) as WebGLRenderingContext);

    if (!gl) {
      console.error("WebGL not supported");
      return;
    }

    const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
    const fs = createShader(gl, gl.FRAGMENT_SHADER, fsSource);

    if (!vs || !fs) return;

    program = gl.createProgram();

    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Program link error:", gl.getProgramInfoLog(program));
      return;
    }

    gl.useProgram(program);

    // Quad
    positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    const positions = new Float32Array([
      -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1,
    ]);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);

    const positionLoc = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

    const timeLoc = gl.getUniformLocation(program, "u_time");
    const audioLoc = gl.getUniformLocation(program, "u_audio");
    const mouseLoc = gl.getUniformLocation(program, "u_mouse");
    const bassLoc = gl.getUniformLocation(program, "u_bass");
    const midLoc = gl.getUniformLocation(program, "u_mid");
    const trebleLoc = gl.getUniformLocation(program, "u_treble");
    const heatLoc = gl.getUniformLocation(program, "u_heat");

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    function tick() {
      if (!gl || !program) return;

      const elapsed = (Date.now() - startTime) / 1000;

      // Audio — real mic level or strong procedural pulse
      let target = audioLevel;
      const now = Date.now();

      if (target === 0 && (status === "listening" || status === "speaking")) {
        // Procedural speech: continuous pulsing with no dead zones
        const t = now * 0.005;
        const env = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 2.8 + Math.sin(t * 5.3) * 0.4));
        target = Math.min(1, env);
      } else if (status === "thinking" || status === "executing") {
        // Processing: slow deep pulse
        const t = now * 0.002;
        target = 0.15 + 0.2 * (0.5 + 0.5 * Math.sin(t * 1.3));
      } else if (status === "idle") {
        // Gentle breathing when idle
        const t = now * 0.001;
        target = 0.03 + Math.sin(t) * 0.015;
      }

      localAudio += (target - localAudio) * 0.35;

      // Simulated frequency bands from single audio level
      const t2 = now * 0.003;
      audioBass += ((target * (0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t2)))) - audioBass) * 0.28;
      audioMid  += ((target * (0.3 + 0.7 * (0.5 + 0.5 * Math.sin(t2 * 2.3)))) - audioMid) * 0.28;
      audioTreble += ((target * (0.2 + 0.8 * (0.5 + 0.5 * Math.sin(t2 * 4.7)))) - audioTreble) * 0.28;

      breathPhase = now * 0.001;

      // Mouse smoothing
      currentMouseX += (mouseX - currentMouseX) * 0.12;
      currentMouseY += (mouseY - currentMouseY) * 0.12;

      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.uniform1f(timeLoc, elapsed * speed);
      gl.uniform1f(audioLoc, localAudio);
      gl.uniform2f(mouseLoc, currentMouseX, currentMouseY);
      gl.uniform1f(bassLoc, audioBass);
      gl.uniform1f(midLoc, audioMid);
      gl.uniform1f(trebleLoc, audioTreble);
      gl.uniform1f(heatLoc, processingHeat);

      gl.drawArrays(gl.TRIANGLES, 0, 6);

      animationFrameId = requestAnimationFrame(tick);
    }

    tick();

    // Clean memory leak-free unmount
    return () => {
      cancelAnimationFrame(animationFrameId);
      if (gl) {
        // Lose WebGL context & delete buffers/programs to prevent GPU & system RAM leaks completely
        const ext = gl.getExtension("WEBGL_lose_context");
        if (ext) ext.loseContext();
        gl.deleteProgram(program);
        if (positionBuffer) gl.deleteBuffer(positionBuffer);
      }
    };
  });
</script>

<div
  class="orb-container"
  class:mini
  role="region"
  aria-label="Luna Opal Portal"
  onmousemove={handleMouseMove}
  onmouseleave={handleMouseLeave}
>
  <div class="orb-wrapper" style="transform: scale({scale});">
    <canvas bind:this={canvas} width="320" height="320" class="orb-canvas"
    ></canvas>
  </div>
</div>

<style>
  .orb-container {
    position: relative;
    width: 260px;
    height: 260px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .orb-container.mini {
    width: 90px;
    height: 90px;
  }

  .orb-wrapper {
    position: absolute;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    /* Soft, luxurious bluish cosmic drop shadow */
    filter: drop-shadow(0 0 45px rgba(38, 209, 250, 0.45))
      drop-shadow(0 0 85px rgba(99, 102, 241, 0.25));
    transition: filter 0.4s ease;
    will-change: transform;
  }

  .orb-canvas {
    width: 100%;
    height: 100%;
    will-change: transform;
  }

  .orb-container.mini .orb-wrapper {
    filter: drop-shadow(0 0 22px rgba(38, 209, 250, 0.6));
  }
</style>
