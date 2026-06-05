#!/usr/bin/env python3
"""
actions/eyes.py — Luna Eyes
Visão de tela + câmeras de segurança com alertas de risco.
"""
import threading
import time
import json
from pathlib import Path
from typing import Optional, Callable

try:
    from vision.screen import ScreenVision
    HAS_SCREEN = True
except ImportError:
    HAS_SCREEN = False

try:
    from brain.llm import get_llm, MODELS
    HAS_LLM = True
except ImportError:
    HAS_LLM = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

TEMP_DIR = Path(__file__).parent.parent / "temp" / "img"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class EyesManager:
    """Gerencia visão de tela e câmeras de segurança."""

    def __init__(self):
        self._llm = get_llm() if HAS_LLM else None
        self._screen = ScreenVision() if HAS_SCREEN else None
        self._cameras: dict[int, cv2.VideoCapture] = {}  # {cam_id: cap}
        self._watch_thread: Optional[threading.Thread] = None
        self._watching = threading.Event()
        self._alert_cb: Optional[Callable[[str], None]] = None

    # ── Visão de tela ─────────────────────────────────────────

    def describe_screen(self) -> str:
        """Captura e descreve o que está na tela."""
        if not self._screen:
            return "Módulo de visão não disponível."
        if not self._screen.capture():
            return "Não consegui capturar a tela."
        text = self._screen.extract_text()
        if not text or not text.strip():
            return "Tela capturada, mas sem texto legível."
        if self._llm:
            prompt = (
                "Descreva brevemente o que está sendo exibido na tela com base no texto abaixo. "
                "Seja conciso (máx 3 frases).\n\n"
                f"Conteúdo da tela:\n{text[:1500]}\n\nDescrição:"
            )
            raw = self._llm.generate(prompt, task_type="factual", model=MODELS.get("fast"))
            try:
                data = json.loads(raw)
                return data.get("response", data.get("description", raw))
            except Exception:
                return raw
        return text[:500]

    # ── Câmeras ───────────────────────────────────────────────

    def add_camera(self, cam_id: int = 0) -> str:
        if not HAS_CV2:
            return "OpenCV não instalado. Execute: pip install opencv-python"
        if cam_id in self._cameras:
            return f"Câmera {cam_id} já está ativa."
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            return f"Não consegui abrir a câmera {cam_id}."
        self._cameras[cam_id] = cap
        return f"📷 Câmera {cam_id} conectada."

    def remove_camera(self, cam_id: int = 0) -> str:
        if cam_id not in self._cameras:
            return f"Câmera {cam_id} não está ativa."
        self._cameras[cam_id].release()
        del self._cameras[cam_id]
        return f"Câmera {cam_id} desconectada."

    def capture_camera(self, cam_id: int = 0) -> Optional[str]:
        """Captura frame da câmera e salva. Retorna caminho ou None."""
        if not HAS_CV2 or cam_id not in self._cameras:
            return None
        cap = self._cameras[cam_id]
        ret, frame = cap.read()
        if not ret:
            return None
        path = str(TEMP_DIR / f"cam_{cam_id}.jpg")
        cv2.imwrite(path, frame)
        return path

    def analyze_camera(self, cam_id: int = 0) -> str:
        """Captura e analisa frame da câmera via LLM (se disponível)."""
        path = self.capture_camera(cam_id)
        if not path:
            return f"Câmera {cam_id} não disponível ou sem frame."
        # Análise via OCR/LLM de texto na imagem (sem modelo de visão)
        if self._llm:
            return f"📷 Frame capturado em {path}. (Análise de imagem requer modelo multimodal)"
        return f"📷 Frame salvo em {path}"

    # ── Vigilância contínua ───────────────────────────────────

    def start_watch(self, cam_id: int = 0, interval: float = 5.0,
                    on_alert: Optional[Callable[[str], None]] = None) -> str:
        """Inicia monitoramento contínuo com detecção de movimento."""
        if not HAS_CV2:
            return "OpenCV não instalado."
        if cam_id not in self._cameras:
            msg = self.add_camera(cam_id)
            if "Não consegui" in msg:
                return msg
        if self._watching.is_set():
            return "Vigilância já está ativa."
        self._alert_cb = on_alert
        self._watching.set()
        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            args=(cam_id, interval),
            daemon=True,
        )
        self._watch_thread.start()
        return f"👁 Vigilância iniciada na câmera {cam_id} (intervalo: {interval}s)"

    def stop_watch(self) -> str:
        self._watching.clear()
        return "Vigilância encerrada."

    def _watch_loop(self, cam_id: int, interval: float):
        cap = self._cameras.get(cam_id)
        if not cap:
            return
        prev_frame = None
        while self._watching.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(interval)
                continue
            if prev_frame is not None and HAS_CV2:
                # Detecção de movimento simples por diferença de frames
                diff = cv2.absdiff(prev_frame, frame)
                gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
                motion_pct = (thresh > 0).mean() * 100
                if motion_pct > 5.0:  # >5% dos pixels mudaram
                    alert = f"⚠ Movimento detectado na câmera {cam_id}! ({motion_pct:.1f}% da imagem)"
                    if self._alert_cb:
                        self._alert_cb(alert)
            prev_frame = frame.copy()
            time.sleep(interval)

    def list_cameras(self) -> str:
        if not self._cameras:
            return "Nenhuma câmera ativa."
        ids = ", ".join(str(i) for i in self._cameras)
        watch = "👁 vigilância ativa" if self._watching.is_set() else "em espera"
        return f"Câmeras ativas: {ids} | {watch}"

    def status(self) -> str:
        lines = ["👁 Luna Eyes"]
        lines.append(f"  Visão de tela: {'✓' if HAS_SCREEN else '✗'}")
        lines.append(f"  OpenCV: {'✓' if HAS_CV2 else '✗ (pip install opencv-python)'}")
        lines.append(f"  Câmeras: {len(self._cameras)}")
        lines.append(f"  Vigilância: {'ativa' if self._watching.is_set() else 'inativa'}")
        return "\n".join(lines)


_eyes: Optional[EyesManager] = None


def get_eyes() -> EyesManager:
    global _eyes
    if _eyes is None:
        _eyes = EyesManager()
    return _eyes
