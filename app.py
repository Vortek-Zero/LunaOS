#!/usr/bin/env python3
"""
app.py — Interface gráfica da Luna (PyQt6)
Sistema de mini widgets parent/child integrado ao HUD.
"""
import sys
import os
import io
os.environ["LC_ALL"] = "C.UTF-8"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
import math
import random
import re
import textwrap
import threading
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLineEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QScrollArea, QTextEdit, QLabel, QFrame, QMessageBox, QInputDialog, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QThread, pyqtSignal, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QRadialGradient

from luna_core import get_luna
from api import start_server_thread


# ══════════════════════════════════════════════════════════════
#  WORKER
# ══════════════════════════════════════════════════════════════

class LunaWorker(QThread):
    status_signal  = pyqtSignal(str)
    chat_signal    = pyqtSignal(str, str)   # (sender, text)
    metrics_signal = pyqtSignal(dict)
    widget_signal  = pyqtSignal(str, dict)  # (widget_type, data)

    def __init__(self):
        super().__init__()
        self.luna = None
        self.command_queue: list = []
        self.running = True

    def run(self):
        self.status_signal.emit("CARREGANDO...")
        try:
            self.luna = get_luna()
            self.status_signal.emit("SISTEMA ONLINE")
            self.chat_signal.emit("Luna", "Sistemas online. Pronta para ajudar.")
        except Exception as e:
            self.status_signal.emit(f"ERRO: {str(e)[:30]}")
            self.chat_signal.emit("SYS", f"Erro ao iniciar: {e}")
            return

        try:
            if self.luna.stt.is_available():
                self.luna.stt.enabled = True
                self.luna.stt.start_wakeword_listener()
        except Exception:
            pass

        while self.running:
            if self.command_queue:
                cmd = self.command_queue.pop(0)
                if isinstance(cmd, tuple) and cmd[0] == "TEXT":
                    self._process(cmd[1])
                elif cmd == "LISTEN":
                    self._listen_and_process()
            elif self.luna and self.luna.stt.wake_event.is_set():
                self.luna.stt.wake_event.clear()
                self._listen_and_process()
            else:
                self.msleep(80)

    def _listen_and_process(self):
        self.status_signal.emit("OUVINDO...")
        text = self.luna.listen()
        if text:
            self.chat_signal.emit("Você", text)
            self._process(text)
        else:
            self.status_signal.emit("SISTEMA ONLINE")
            try:
                self.luna.stt.start_wakeword_listener()
            except Exception:
                pass

    def _process(self, text: str):
        self.status_signal.emit("PENSANDO...")
        response = self.luna.process(text)
        self.metrics_signal.emit(self.luna.last_metrics)
        self.chat_signal.emit("Luna", response)
        # Detecta widgets a criar com base no texto e resposta
        self._detect_widget(text, response)
        self.status_signal.emit("FALANDO...")
        self.luna.speak(response)
        self.status_signal.emit("SISTEMA ONLINE")
        try:
            if self.luna.voice_input_enabled:
                self.luna.stt.start_wakeword_listener()
        except Exception:
            pass

    def _detect_widget(self, user_text: str, response: str):
        """Analisa o texto e emite signal para criar o widget adequado."""
        tl = user_text.lower()

        # ── Luna Writing ───────────────────────────────────────
        writing_open = ["vamos escrever", "modo escrita", "luna writing", "abrir editor",
                        "abre o editor", "quero escrever"]
        writing_close = ["fecha o editor", "fecha a escrita", "sai do editor", "fechar editor"]
        if any(w in tl for w in writing_open):
            self.widget_signal.emit("open_writing", {})
            return
        if any(w in tl for w in writing_close):
            self.widget_signal.emit("close_writing", {})
            return

        # ── Luna Math ──────────────────────────────────────────
        math_open = ["vamos calcular", "modo matematica", "modo matemática", "luna math",
                     "abre a lousa", "abrir lousa", "quero calcular"]
        math_close = ["fecha a lousa", "fecha o math", "sai da lousa", "fechar lousa"]
        if any(w in tl for w in math_open):
            # Extrai expressão inline se houver: "vamos calcular 2+2"
            import re as _re
            m = _re.search(r'(?:calcular|calcula)\s+(.+)', tl)
            expr = m.group(1).strip() if m else ""
            self.widget_signal.emit("open_math", {"expr": expr})
            return
        if any(w in tl for w in math_close):
            self.widget_signal.emit("close_math", {})
            return

        # Timer — exige palavra-chave explícita de timer no input OU na resposta com ⏱
        timer_kw = ["timer", "alarme", "cronômetro", "conta regressiva", "me avisa em", "avisa em", "daqui a", "daqui em"]
        is_timer_request = any(w in tl for w in timer_kw) or ("⏱" in response and "timer" in response.lower())
        if is_timer_request:
            dm = re.search(r'(\d+)\s*(minuto|segundo|hora)', tl)
            if dm:
                n, unit = int(dm.group(1)), dm.group(2)
                secs = n * (3600 if "hora" in unit else 60 if "minuto" in unit else 1)
                name_m = re.search(r'para a (.+)|para o (.+)|do (.+)|da (.+)', tl)
                
                # Coleta o nome capturado sem o "para"
                name = "timer"
                if name_m:
                    for g in name_m.groups():
                        if g:
                            name = g.strip()
                            break

                self.widget_signal.emit("timer", {"seconds": secs, "name": name})
            return

        # Nota
        if any(w in tl for w in ["anota", "anote", "nota:"]):
            m2 = re.search(r'(?:anota|anote|nota:)\s*[:\s](.+)', tl)
            content = m2.group(1).strip() if m2 else user_text
            self.widget_signal.emit("note", {"text": content})
            return

        # Lembrete
        if "🔔" in response and "lembrete" in response.lower():
            self.widget_signal.emit("reminder", {"text": response})
            return

        # Clima
        if "🌤" in response or "temperatura" in response.lower():
            self.widget_signal.emit("weather", {"text": response})
            return

        # Música
        if any(c in response for c in ["▶", "⏸", "⏭", "⏮", "🔊", "🔉"]):
            self.widget_signal.emit("music", {"text": response})
            return

        # Foco
        if "🎯" in response and "foco" in response.lower():
            m3 = re.search(r'(\d+)\s*minuto', response.lower())
            mins = int(m3.group(1)) if m3 else 25
            self.widget_signal.emit("focus", {"minutes": mins})
            return

    def stop(self):
        self.running = False


# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
#  MINI WIDGETS — Renderizados no painel lateral
# ══════════════════════════════════════════════════════════════

FONT_MONO = "Ubuntu"
_active_widgets: list = []

class BaseMiniWidget(QWidget):
    """Widget embutido no painel lateral — sem janela flutuante."""
    closed_signal = pyqtSignal()

    def __init__(self, w: int, h: int, accent: QColor, ttl: int = 0):
        super().__init__()
        self.setFixedSize(w, h)
        self.accent = accent
        self._ttl = ttl
        self._born_ts = datetime.now().timestamp()
        _active_widgets.append(self)

        if ttl > 0:
            self._life_timer = QTimer(self)
            self._life_timer.timeout.connect(self._tick_life)
            self._life_timer.start(1000)

    def _tick_life(self):
        if datetime.now().timestamp() - self._born_ts >= self._ttl:
            self.close_widget()

    def close_widget(self):
        if self in _active_widgets:
            _active_widgets.remove(self)
        self.closed_signal.emit()
        self.setParent(None)
        self.deleteLater()

    def mouseDoubleClickEvent(self, e):
        self.close_widget()

    def _paint_base(self, p: QPainter):
        # Tenta pegar a cor central
        try:
            cr = self.window().console.color_r
            cg = self.window().console.color_g
            cb = self.window().console.color_b
            self.bg_color = QColor(int(cr), int(cg), int(cb), 50)
        except Exception:
            self.bg_color = QColor(8, 4, 20, 235)

        r = 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self.bg_color))
        p.setPen(QPen(self.accent, 1))
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, r, r)
        p.setPen(QPen(self.accent, 2))
        p.drawLine(r, 1, self.width()-r, 1)

    def _draw_header(self, p: QPainter, icon: str, title: str):
        f = QFont(FONT_MONO, 7)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(self.accent, 1))
        p.drawText(9, 14, f"{icon} {title.upper()}")
        p.setPen(QPen(QColor(100, 80, 130, 120), 1))
        p.setFont(QFont(FONT_MONO, 6))
        p.drawText(self.width()-28, 13, "2×✕")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)


# ── Timer Widget ──────────────────────────────────────────────

class TimerWidget(BaseMiniWidget):
    def __init__(self, seconds: int, name: str = "timer"):
        # Aumentamos a altura de 72 para 110 para caber os botões
        super().__init__(150, 110, QColor(0, 200, 255, 220))
        self._total = seconds
        self._remaining = seconds
        self._name = name[:18]
        self._done = False
        
        # Audio Player
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PyQt6.QtCore import QUrl
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._player.setSource(QUrl.fromLocalFile("/home/pera/Luna/sounds/alarm-timeralert.mp3"))
        self._player.setLoops(-1)  # Infinite loop
        
        # Botões
        from PyQt6.QtWidgets import QPushButton
        self.btn_stop = QPushButton("Parar", self)
        self.btn_stop.setGeometry(10, 80, 60, 20)
        self.btn_stop.setStyleSheet("background-color:#600; color:white; border-radius:5px; font-family:Ubuntu; font-size:10px;")
        self.btn_stop.clicked.connect(self.close_widget)
        self.btn_stop.hide()

        self.btn_repeat = QPushButton("Repetir", self)
        self.btn_repeat.setGeometry(80, 80, 60, 20)
        self.btn_repeat.setStyleSheet("background-color:#060; color:white; border-radius:5px; font-family:Ubuntu; font-size:10px;")
        self.btn_repeat.clicked.connect(self._repeat)
        self.btn_repeat.hide()

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)

    def _repeat(self):
        self._player.stop()
        self._remaining = self._total
        self._done = False
        self.btn_stop.hide()
        self.btn_repeat.hide()
        self.update()

    def close_widget(self):
        if hasattr(self, '_player'):
            self._player.stop()
        super().close_widget()

    def _tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self.update()
        else:
            if not self._done:
                self._done = True
                self.btn_stop.show()
                self.btn_repeat.show()
                self._player.play()
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)
        self._draw_header(p, "⏱", self._name)

        if self._done:
            p.setFont(QFont(FONT_MONO, 12, QFont.Weight.Bold))
            p.setPen(QPen(QColor(255, 80, 80, 230)))
            p.drawText(QRect(0, 20, self.width(), 30), Qt.AlignmentFlag.AlignCenter, "PRONTO!")
        else:
            mins, secs = divmod(self._remaining, 60)
            hrs, mins2 = divmod(mins, 60)
            ts = f"{hrs:02d}:{mins2:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"
            p.setFont(QFont(FONT_MONO, 18, QFont.Weight.Bold))
            p.setPen(QPen(QColor(0, 220, 255, 240)))
            p.drawText(QRect(0, 18, self.width(), 34), Qt.AlignmentFlag.AlignCenter, ts)

        # Barra de progresso
        prog = 1.0 - self._remaining / max(1, self._total)
        bw = int((self.width()-16) * prog)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 60, 80, 80)))
        p.drawRoundedRect(8, 60, self.width()-16, 6, 3, 3)
        if bw > 0:
            p.setBrush(QBrush(QColor(0, 200, 255, 180)))
            p.drawRoundedRect(8, 60, bw, 6, 3, 3)


# ── Note Widget (post-it) ─────────────────────────────────────

class NoteWidget(BaseMiniWidget):
    def __init__(self, text: str):
        lines = textwrap.wrap(text, width=20)
        h = max(72, 30 + len(lines)*15 + 10)
        super().__init__(155, h, QColor(255, 215, 50, 220))
        self._lines = lines

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Fundo post-it
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 60)))
        p.drawRoundedRect(3, 3, self.width(), self.height(), 6, 6)
        p.setBrush(QBrush(QColor(28, 25, 4, 240)))
        p.setPen(QPen(QColor(255, 215, 50, 200), 1))
        p.drawRoundedRect(0, 0, self.width()-1, self.height()-1, 6, 6)
        p.setPen(QPen(QColor(255, 215, 50, 220), 2))
        p.drawLine(6, 1, self.width()-6, 1)

        self._draw_header(p, "📝", "nota")
        p.setFont(QFont(FONT_MONO, 9))
        p.setPen(QPen(QColor(255, 240, 150, 230)))
        for i, line in enumerate(self._lines):
            p.drawText(9, 28 + i*15, line)


# ── Clock Widget ──────────────────────────────────────────────

class ClockWidget(BaseMiniWidget):
    def __init__(self):
        super().__init__(120, 120, QColor(180, 140, 255, 220))
        t = QTimer(self)
        t.timeout.connect(self.update)
        t.start(1000)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)
        self._draw_header(p, "🕐", "hora")

        now = datetime.now()
        cx, cy, r = self.width()//2, self.height()//2 + 6, 40

        p.setPen(QPen(QColor(180, 140, 255, 80), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        p.setPen(QPen(QColor(180, 140, 255, 140), 2))
        for i in range(12):
            a = math.radians(i*30 - 90)
            p.drawLine(int(cx+(r-5)*math.cos(a)), int(cy+(r-5)*math.sin(a)),
                       int(cx+r*math.cos(a)),     int(cy+r*math.sin(a)))

        def hand(deg, length, color, width):
            a = math.radians(deg - 90)
            p.setPen(QPen(color, width))
            p.drawLine(cx, cy, int(cx+length*math.cos(a)), int(cy+length*math.sin(a)))

        hand((now.hour%12)*30 + now.minute*0.5, r*0.55, QColor(200,170,255,220), 2)
        hand(now.minute*6,  r*0.78, QColor(220,200,255,220), 1)
        hand(now.second*6,  r*0.85, QColor(255,80,80,200),   1)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(200,170,255,220)))
        p.drawEllipse(QPointF(cx, cy), 3, 3)

        p.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        p.setPen(QPen(QColor(200,170,255,200)))
        p.drawText(QRect(0, self.height()-16, self.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, now.strftime("%H:%M:%S"))


# ── Reminder Widget ───────────────────────────────────────────

class ReminderWidget(BaseMiniWidget):
    def __init__(self, text: str):
        clean = text.replace("🔔","").replace("Lembrete criado:","").strip()
        lines = textwrap.wrap(clean, width=20)
        h = max(68, 30 + len(lines)*15 + 8)
        super().__init__(155, h, QColor(255, 160, 50, 220), ttl=20)
        self._lines = lines

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)
        self._draw_header(p, "🔔", "lembrete")
        p.setFont(QFont(FONT_MONO, 9))
        p.setPen(QPen(QColor(255, 200, 120, 230)))
        for i, line in enumerate(self._lines):
            p.drawText(9, 28 + i*15, line)


# ── Weather Widget ────────────────────────────────────────────

class WeatherWidget(BaseMiniWidget):
    def __init__(self, text: str):
        lines = [l.strip() for l in text.split("\n") if l.strip()][:5]
        h = max(80, 28 + len(lines)*14 + 8)
        super().__init__(175, h, QColor(80, 200, 255, 220), ttl=1800)
        self._lines = lines

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)
        self._draw_header(p, "🌤", "clima")
        p.setFont(QFont(FONT_MONO, 8))
        p.setPen(QPen(QColor(160, 230, 255, 230)))
        for i, line in enumerate(self._lines):
            p.drawText(7, 26 + i*14, line[:28])


# ── Music Widget ──────────────────────────────────────────────

class MusicWidget(BaseMiniWidget):
    def __init__(self, text: str):
        super().__init__(165, 62, QColor(200, 80, 255, 220))
        self._text = text.strip()

    @property
    def _bars(self):
        try:
            return self.window().console._bars
        except Exception:
            return [0]*14

    def update_text(self, text: str):
        self._text = text.strip()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)
        self._draw_header(p, "🎵", "música")
        p.setFont(QFont(FONT_MONO, 8))
        p.setPen(QPen(QColor(220, 160, 255, 230)))
        short = self._text[:24] + ("…" if len(self._text)>24 else "")
        p.drawText(8, 28, short)
        # Equalizer (Cava)
        bx = 8
        for i in range(14):
            # cava output 0-30 range. scale to 0-30 px height
            # +3px mínimo para as barras não sumirem
            bh = 3 + min(30, self._bars[i])
            
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(200,80,255,160) if i%2==0 else QColor(160,60,220,140)))
            
            # desenha a barra partindo do chão (Y=54)
            p.drawRect(bx, 54-bh, 7, bh)
            bx += 10

# ── Focus Widget ──────────────────────────────────────────────

class FocusWidget(BaseMiniWidget):
    def __init__(self, minutes: int = 25):
        super().__init__(150, 76, QColor(80, 255, 160, 220))
        self._total = minutes * 60
        self._remaining = self._total
        self._done = False
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)

    def _tick(self):
        if self._remaining > 0:
            self._remaining -= 1
            self.update()
        else:
            self._done = True
            self.update()
            QTimer.singleShot(8000, self.close_widget)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_base(p)
        self._draw_header(p, "🎯", "foco")

        if self._done:
            p.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
            p.setPen(QPen(QColor(80, 255, 160, 230)))
            p.drawText(QRect(0, 20, self.width(), 30), Qt.AlignmentFlag.AlignCenter, "CONCLUÍDO!")
        else:
            mins, secs = divmod(self._remaining, 60)
            p.setFont(QFont(FONT_MONO, 17, QFont.Weight.Bold))
            p.setPen(QPen(QColor(80, 255, 160, 240)))
            p.drawText(QRect(0, 16, self.width(), 34), Qt.AlignmentFlag.AlignCenter,
                       f"{mins:02d}:{secs:02d}")

        prog = 1.0 - self._remaining / max(1, self._total)
        bw = int((self.width()-16) * prog)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(20, 80, 40, 80)))
        p.drawRoundedRect(8, 64, self.width()-16, 6, 3, 3)
        if bw > 0:
            p.setBrush(QBrush(QColor(80, 255, 160, 180)))
            p.drawRoundedRect(8, 64, bw, 6, 3, 3)


# ══════════════════════════════════════════════════════════════
#  WIDGET MANAGER — gerencia os widgets do painel lateral
# ══════════════════════════════════════════════════════════════
from PyQt6.QtCore import QObject, pyqtSignal

class WidgetsSidePanel(QWidget):
    """Painel lateral direito que exibe os mini widgets embutidos."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: rgba(0,0,0,40);")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 8, 8)
        root.setSpacing(5)

        hdr = QHBoxLayout()
        lbl = QLabel("LUNA — WIDGETS")
        lbl.setFont(QFont("Ubuntu", 10, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #00d4ff;")
        hdr.addWidget(lbl)
        hdr.addStretch()
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #004060;")
        root.addWidget(sep)

        # ScrollArea para os widgets embutidos
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:#000008;border:none;}"
                             "QScrollBar:vertical{width:4px;background:#000;}"
                             "QScrollBar::handle:vertical{background:#004060;border-radius:2px;}")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        scroll.setWidget(self._container)
        root.addWidget(scroll, stretch=1)

        self.lbl_empty = QLabel("nenhum widget ativo")
        self.lbl_empty.setStyleSheet("color: #336; font-family: Ubuntu; font-size: 8pt;")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_empty)

        self.btn_exit = QPushButton("◄ fechar")
        self.btn_exit.setFixedHeight(18)
        self.btn_exit.setStyleSheet(
            "QPushButton{background:transparent;color:#ff5555;border:none;"
            "font-family:Ubuntu;font-size:7pt;text-align:left;}"
            "QPushButton:hover{color:#ff8888;}"
        )
        root.addWidget(self.btn_exit)

    def add_widget(self, w: BaseMiniWidget):
        """Insere o widget no painel antes do stretch."""
        w.setFixedWidth(self.width() - 28)
        self._layout.insertWidget(self._layout.count() - 1, w)
        w.closed_signal.connect(lambda: self._on_closed())
        self.lbl_empty.setVisible(False)

    def _on_closed(self):
        self.lbl_empty.setVisible(self._layout.count() <= 1)  # só o stretch

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Ajusta largura dos widgets ao redimensionar o painel
        for i in range(self._layout.count() - 1):
            item = self._layout.itemAt(i)
            if item and item.widget():
                item.widget().setFixedWidth(self.width() - 28)


class WidgetManager(QObject):
    """Gerencia criação e inserção de mini widgets no painel lateral."""

    def __init__(self, main_window: QMainWindow):
        super().__init__()
        self._main = main_window
        self._clock: ClockWidget | None = None
        self._music: MusicWidget | None = None
        self._weather: WeatherWidget | None = None

    @property
    def _panel(self) -> "WidgetsSidePanel":
        return self._main.widgets_panel

    def _add(self, w: BaseMiniWidget):
        self._panel.add_widget(w)
        if not self._main._in_widgets:
            self._main._open_widgets_panel()

    def _on_closed(self, w):
        if w == self._clock:  self._clock = None
        if w == self._music:  self._music = None
        if w == self._weather: self._weather = None

    def spawn_timer(self, seconds: int, name: str = "timer"):
        w = TimerWidget(seconds, name)
        w.closed_signal.connect(lambda: self._on_closed(w))
        self._add(w)

    def spawn_note(self, text: str):
        w = NoteWidget(text)
        self._add(w)

    def spawn_reminder(self, text: str):
        w = ReminderWidget(text)
        self._add(w)

    def spawn_weather(self, text: str):
        if self._weather:
            self._weather.close_widget()
        self._weather = WeatherWidget(text)
        self._weather.closed_signal.connect(lambda: self._on_closed(self._weather))
        self._add(self._weather)

    def spawn_music(self, text: str):
        if self._music:
            self._music.update_text(text)
            return
        self._music = MusicWidget(text)
        self._music.closed_signal.connect(lambda: self._on_closed(self._music))
        self._add(self._music)

    def spawn_focus(self, minutes: int):
        for old in [x for x in _active_widgets if isinstance(x, FocusWidget)]:
            old.close_widget()
        w = FocusWidget(minutes)
        self._add(w)

    def toggle_clock(self):
        if self._clock:
            self._clock.close_widget()
            self._clock = None
        else:
            self._clock = ClockWidget()
            self._clock.closed_signal.connect(lambda: self._on_closed(self._clock))
            self._add(self._clock)

    def handle_widget_signal(self, wtype: str, data: dict):
        if wtype == "timer":
            self.spawn_timer(data.get("seconds", 60), data.get("name", "timer"))
        elif wtype == "note":
            self.spawn_note(data.get("text", ""))
        elif wtype == "reminder":
            self.spawn_reminder(data.get("text", ""))
        elif wtype == "weather":
            self.spawn_weather(data.get("text", ""))
        elif wtype == "music":
            self.spawn_music(data.get("text", ""))
        elif wtype == "focus":
            self.spawn_focus(data.get("minutes", 25))
        elif wtype == "clock":
            self.toggle_clock()


# ══════════════════════════════════════════════════════════════
#  HUD PRINCIPAL
# ══════════════════════════════════════════════════════════════

class LunaConsoleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background-color: #000000;")

        self.cx = 210
        self.cy = 300
        self.ai_status = "INICIALIZANDO..."
        self.tails = 3
        self.last_time = 0.0
        self.last_model = "N/A"
        self.color_r, self.color_g, self.color_b = 0.0, 200.0, 255.0
        self.chat_history: list[tuple[str, str]] = []
        self.conv_mode = False

        # Worker
        self.worker = LunaWorker()
        self.worker.status_signal.connect(self._update_status)
        self.worker.chat_signal.connect(self._update_chat)
        self.worker.metrics_signal.connect(self._update_metrics)
        self.worker.start()

        # Widget manager — inicializado depois em LunaWindow
        self.wm: WidgetManager | None = None

        # Conecta signal do worker ao manager (feito em LunaWindow após wm ser criado)

        # Visual
        self.time = 0.0
        self.sun_pulse = 1.0
        self.pulse_dir = 1
        self.luna_pulse = 0.0

        # Cava / Glava Audio Visualizer integration
        self._bars = [0] * 14
        self._cava_proc = None
        self._setup_cava()

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)

        self.console_font = QFont("Ubuntu", 8)
        self.console_font.setBold(True)
        self.title_font = QFont("Ubuntu", 24)
        self.title_font.setBold(True)
        self.chat_font = QFont("Ubuntu", 9)
        self.chat_font.setBold(True)

        # Input
        self.input_box = QLineEdit(self)
        self.input_box.setGeometry(20, 700, 380, 30)
        self._update_styles(0, 200, 255)
        self.input_box.setPlaceholderText("Digite ou diga 'Ei Luna'...")
        self.input_box.returnPressed.connect(self._send_input)

        # Botão relógio (toggle clock widget)
        self.btn_clock = QPushButton("🕐", self)
        self.btn_clock.setGeometry(390, 10, 24, 24)
        self.btn_clock.setToolTip("Mostrar/ocultar relógio")
        self.btn_clock.setStyleSheet(
            "QPushButton { background:transparent; border:none; font-size:14px; }"
            "QPushButton:hover { background:#1a0a2a; border-radius:4px; }"
        )
        self.btn_clock.clicked.connect(lambda: self.wm.toggle_clock() if self.wm else None)

        self.setFocus()

    def _setup_cava(self):
        import tempfile
        import os
        from PyQt6.QtCore import QProcess

        conf = """[general]
bars = 14
framerate = 60
[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 30
"""
        self._conf_path = os.path.join(tempfile.gettempdir(), "luna_main_cava.conf")
        with open(self._conf_path, "w") as f:
            f.write(conf)
            
        self._cava_proc = QProcess(self)
        self._cava_proc.readyReadStandardOutput.connect(self._read_cava)
        self._cava_proc.start("cava", ["-p", self._conf_path])

    def _read_cava(self):
        if not self._cava_proc: return
        data = self._cava_proc.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        lines = data.strip().split('\n')
        if not lines: return
        
        last_line = lines[-1].strip()
        vals = [v for v in last_line.split(';') if v.isdigit()]
        if len(vals) >= 14:
            self._bars = [int(v) for v in vals[:14]]



    def _update_styles(self, r, g, b):
        self.input_box.setStyleSheet(
            f"background-color:#0d0d1a;color:rgb({r},{g},{b});"
            f"border:1px solid rgb({int(r/2)},{int(g/2)},{int(b/2)});font-family:Ubuntu;font-size:10pt;"
            "padding: 2px 6px;"
        )

    def _update_status(self, text: str):
        self.ai_status = text

    def _update_metrics(self, metrics: dict):
        self.tails = metrics.get("tails", 3)
        self.last_time = metrics.get("time_ms", 0)
        self.last_model = metrics.get("model", "N/A")

    def _update_chat(self, sender: str, text: str):
        self.chat_history.append((sender, text))
        if len(self.chat_history) > 4:
            self.chat_history.pop(0)

    def _send_input(self):
        text = self.input_box.text().strip()
        if text and self.ai_status == "SISTEMA ONLINE":
            self.worker.command_queue.append(("TEXT", text))
            self.input_box.clear()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and self.ai_status == "SISTEMA ONLINE":
            self.worker.command_queue.append("LISTEN")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Reposiciona input e botão
        self.input_box.setGeometry(20, self.height() - 40, self.width() - 40, 30)
        self.btn_clock.setGeometry(self.width() - 30, 10, 24, 24)



    def _tick(self):
        w, h = self.width(), self.height()
        self.cx = w / 2
        self.cy = h / 2 - 40
        self.time += 0.02
        self.luna_pulse += 0.03

        if "ERRO" in self.ai_status:
            tr, tg, tb = 255, 50, 50
        elif "PENSANDO" in self.ai_status:
            tr, tg, tb = (220, 170, 255) if self.conv_mode else (50, 255, 120)
        elif self.conv_mode:
            tr, tg, tb = 200, 150, 255
        else:
            tr, tg, tb = 0, 200, 255

        self.color_r += (tr - self.color_r) * 0.1
        self.color_g += (tg - self.color_g) * 0.1
        self.color_b += (tb - self.color_b) * 0.1

        # Sincronia Cava -> Sol
        avg_bar = sum(self._bars) / max(1, len(self._bars)) if hasattr(self, '_bars') else 0
        
        pulse_speed = 0.08 if "FALANDO" in self.ai_status else 0.01
        pulse_min   = 0.70 if "FALANDO" in self.ai_status else 0.88
        pulse_max   = 1.35 if "FALANDO" in self.ai_status else 1.12

        if avg_bar > 0:
            target_pulse = 0.88 + (avg_bar / 30.0) * 0.8
            self.sun_pulse += (target_pulse - self.sun_pulse) * 0.3
        else:
            self.sun_pulse += pulse_speed * self.pulse_dir
            if self.sun_pulse >= pulse_max:
                self.sun_pulse = pulse_max; self.pulse_dir = -1
            elif self.sun_pulse <= pulse_min:
                self.sun_pulse = pulse_min; self.pulse_dir = 1

        # Atualiza a cor dos painéis flutuantes
        color_css = f"rgba({int(self.color_r)}, {int(self.color_g)}, {int(self.color_b)}, 255)"
        if self.wm and hasattr(self.wm, '_panel') and self.wm._panel:
            try:
                self.wm._panel.setStyleSheet(f"background-color: rgba(0,0,0,40); color: {color_css};")
                self.wm._panel.lbl_empty.setStyleSheet(f"color: {color_css}; font-family: Ubuntu; font-size: 8pt;")
            except RuntimeError:
                pass
        
        try:
            if hasattr(self.window(), 'chat_panel'):
                self.window().chat_panel.setStyleSheet(f"background-color: transparent; color: {color_css};")
        except RuntimeError:
            pass

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = self.cx, self.cy
        
        # Deep dark background (#0a0a14) with subtle radial gradient
        bg_gradient = QRadialGradient(cx, cy, w)
        bg_gradient.setColorAt(0.0, QColor(20, 20, 35))
        bg_gradient.setColorAt(1.0, QColor(6, 6, 12))
        painter.fillRect(0, 0, w, h, bg_gradient)
        
        cr, cg, cb = int(self.color_r), int(self.color_g), int(self.color_b)

        # Título
        np_ = 0.5 + 0.5 * math.sin(self.luna_pulse)
        painter.setFont(self.title_font)
        # Glow
        for i in range(5):
            painter.setPen(QPen(QColor(139, 92, 246, 30 - i * 5), 1))
            painter.drawText(80, 60 + i, "LUNA")
        painter.setPen(QPen(QColor(6, 182, 212, 240), 2))
        painter.drawText(80, 60, "LUNA")

        painter.setPen(QPen(QColor(139, 92, 246, 80), 1))
        painter.drawLine(70, 70, 170, 70)

        # ── Shader Reminder Fluid Orb ──
        base_r = 70 * self.sun_pulse
        avg_bar = sum(self._bars) / max(1, len(self._bars)) if hasattr(self, '_bars') else 0
        glow_radius = base_r + 20 + min(120, avg_bar * 4.0)

        painter.setPen(Qt.PenStyle.NoPen)
        
        # Outer glow (Reactive to audio)
        glow_grad = QRadialGradient(cx, cy, glow_radius)
        glow_grad.setColorAt(0.0, QColor(cr, cg, cb, 60))
        glow_grad.setColorAt(0.4, QColor(139, 92, 246, 20))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        # Inner fluid blobs (Simulating liquid morphing using offset ellipses over time)
        blob_colors = [
            (QColor(139, 92, 246, 180), 0.7, 0.4), # Violet
            (QColor(6, 182, 212, 180), 0.5, 0.8),  # Cyan
            (QColor(cr, cg, cb, 220), 0.9, 0.2)    # Main State Color
        ]
        
        for i, (b_color, sp_x, sp_y) in enumerate(blob_colors):
            # Calculate fluid offsets
            ox = math.sin(self.time * sp_x + i) * (base_r * 0.25)
            oy = math.cos(self.time * sp_y + i) * (base_r * 0.25)
            
            blob_grad = QRadialGradient(cx + ox, cy + oy, base_r * 1.2)
            blob_grad.setColorAt(0.0, b_color)
            blob_grad.setColorAt(0.8, QColor(b_color.red(), b_color.green(), b_color.blue(), 20))
            blob_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            
            painter.setBrush(QBrush(blob_grad))
            painter.drawEllipse(QPointF(cx + ox, cy + oy), base_r * 1.1, base_r * 1.1)

        # Core Solid Sphere (Glassy)
        core_grad = QRadialGradient(cx - base_r*0.3, cy - base_r*0.3, base_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 200))
        core_grad.setColorAt(0.3, QColor(cr, cg, cb, 220))
        core_grad.setColorAt(1.0, QColor(cr, cg, cb, 100))
        
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), base_r * 0.8, base_r * 0.8)

        self._update_styles(cr, cg, cb)

        # Chat HUD
        if not self.conv_mode:
            chat_y = h - 145
            painter.setFont(self.chat_font)
            for sender, msg in self.chat_history:
                wrapped = textwrap.wrap(msg, width=46)
                if sender.lower() in ("você", "you"):
                    painter.setPen(QPen(QColor(255, 255, 255, 200)))
                    prefix = "> "
                else:
                    painter.setPen(QPen(QColor(cr, cg, cb, 255)))
                    prefix = "Luna: "
                for i, line in enumerate(wrapped[:3]):
                    txt = prefix + line if i == 0 else "      " + line
                    painter.drawText(20, chat_y, txt)
                    chat_y += 15

        # Dica
        if not self.conv_mode and self.ai_status == "SISTEMA ONLINE" and int(self.time*4) % 2 == 0:
            painter.setPen(QPen(QColor(cr, cg, cb, 100)))
            painter.drawText(20, h - 48, "[ESPAÇO] microfone · [ENTER] enviar texto")

        # Status bar
        painter.setPen(QPen(QColor(cr, cg, cb, 40), 1))
        painter.drawLine(10, h - 22, w - 10, h - 22)
        painter.setPen(QPen(QColor(cr, cg, cb, 150), 1))
        painter.setFont(QFont("Ubuntu", 7))
        timer_str = f"{int(self.time*10)%100:02d}:{int(self.time*100)%60:02d}"
        painter.drawText(15, h - 18, f"SYS: {self.ai_status} | CAUDAS: {self.tails} | T:{timer_str}")
        painter.drawText(15, h - 8,  f"MOD: {self.last_model} | LAST: {self.last_time:.0f}ms")


# ══════════════════════════════════════════════════════════════
#  PAINEL DE CHAT LATERAL
# ══════════════════════════════════════════════════════════════

PR, PG, PB  = 200, 150, 255
CSS_PURPLE  = f"rgb({PR},{PG},{PB})"
CSS_DPURPLE = "rgb(120,80,180)"


class LunaChatPanel(QWidget):
    def __init__(self, worker: LunaWorker):
        super().__init__()
        self.worker = worker
        self.setStyleSheet("background-color: rgba(0,0,0,40);")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 8, 8)
        root.setSpacing(5)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("LUNA — MODO PAPO")
        lbl.setFont(QFont("Ubuntu", 10, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color:{CSS_PURPLE};")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(22, 22)
        self.btn_settings.setStyleSheet(
            f"QPushButton{{background:#080808;color:{CSS_PURPLE};border:1px solid {CSS_DPURPLE};"
            f"border-radius:3px;font-weight:bold;font-size:13px;}}"
            f"QPushButton:hover{{background:#1a0a2a;}}"
        )
        self.btn_settings.clicked.connect(self._show_settings_menu)
        hdr.addWidget(self.btn_settings)

        self.btn_new = QPushButton("+")
        self.btn_new.setFixedSize(22, 22)
        self.btn_new.setStyleSheet(
            f"QPushButton{{background:#080808;color:{CSS_PURPLE};border:1px solid {CSS_DPURPLE};"
            f"border-radius:3px;font-weight:bold;font-size:13px;}}"
            f"QPushButton:hover{{background:#1a0a2a;}}"
        )
        self.btn_new.clicked.connect(self._new_session)
        hdr.addWidget(self.btn_new)
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{CSS_DPURPLE};")
        root.addWidget(sep)

        # Lista de sessões
        self.session_list = QListWidget()
        self.session_list.setMaximumHeight(90)
        self.session_list.setStyleSheet(
            f"QListWidget{{background:#030008;border:none;color:{CSS_PURPLE};"
            f"font-family:Ubuntu;font-size:8pt;}}"
            f"QListWidget::item{{padding:4px 5px;border-radius:3px;}}"
            f"QListWidget::item:selected{{background:#1a0035;}}"
            f"QListWidget::item:hover{{background:#100025;}}"
        )
        self.session_list.itemClicked.connect(self._switch_session)
        self.session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._show_context_menu)
        root.addWidget(self.session_list)

        # Display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "QTextEdit{background:#000008;border:none;"
            "font-family:'Ubuntu',monospace;font-size:11pt;"
            "color:#e0e0e0;padding:8px;}"
        )
        root.addWidget(self.chat_display, stretch=1)

        self.lbl_status = QLabel("● modo papo ativo")
        self.lbl_status.setStyleSheet(f"color:{CSS_PURPLE};font-family:Ubuntu;font-size:7pt;")
        root.addWidget(self.lbl_status)

        # Input
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Digite sua mensagem...")
        self.chat_input.setStyleSheet(
            f"QLineEdit{{background:#0a0015;color:{CSS_PURPLE};"
            f"border:1px solid {CSS_DPURPLE};border-radius:5px;"
            f"font-family:Ubuntu;font-size:10pt;padding:8px;}}"
            f"QLineEdit:focus{{border:1px solid {CSS_PURPLE};}}"
        )
        self.chat_input.returnPressed.connect(self._send)
        input_row.addWidget(self.chat_input)

        self.btn_send = QPushButton("↑")
        self.btn_send.setFixedSize(36, 36)
        self.btn_send.setStyleSheet(
            f"QPushButton{{background:{CSS_PURPLE};color:#000;border-radius:5px;"
            f"font-size:16px;font-weight:bold;border:none;}}"
            f"QPushButton:hover{{background:#ffffff;}}"
        )
        self.btn_send.clicked.connect(self._send)
        input_row.addWidget(self.btn_send)
        root.addLayout(input_row)

        self.btn_exit = QPushButton("◄ sair")
        self.btn_exit.setFixedHeight(18)
        self.btn_exit.setStyleSheet(
            "QPushButton{background:transparent;color:#ff5555;border:none;"
            "font-family:Ubuntu;font-size:7pt;text-align:left;}"
            "QPushButton:hover{color:#ff8888;}"
        )
        root.addWidget(self.btn_exit)

        self.worker.chat_signal.connect(self._on_chat)
        self.worker.status_signal.connect(self._on_status)

    def _load(self):
        try:
            mem = get_luna()._memory
            self.session_list.clear()
            for sid in mem.get_sessions():
                self.session_list.addItem(sid)
            for i in range(self.session_list.count()):
                if self.session_list.item(i).text() == mem.current_session_id:
                    self.session_list.setCurrentRow(i)
                    break
            self._refresh()
        except Exception:
            pass

    def _new_session(self):
        import uuid
        try:
            sid = "Papo-" + str(uuid.uuid4())[:5].upper()
            get_luna()._memory.create_session(sid)
            self._load()
        except Exception:
            pass

    def _switch_session(self, item):
        try:
            get_luna()._memory.switch_session(item.text())
            self._refresh()
        except Exception:
            pass

    def _show_settings_menu(self):
        item = self.session_list.currentItem()
        if not item:
            return
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu{{background-color:#0d001a;color:{CSS_PURPLE};border:1px solid {CSS_DPURPLE};}}"
            f"QMenu::item:selected{{background-color:#1a0035;}}"
        )
        rename_a = menu.addAction("Renomear")
        delete_a = menu.addAction("Apagar espaço")
        action = menu.exec(self.btn_settings.mapToGlobal(
            QPointF(0, self.btn_settings.height()).toPoint()))
        if action == rename_a:
            self._rename_session(item)
        elif action == delete_a:
            self._delete_session(item)

    def _show_context_menu(self, position):
        item = self.session_list.itemAt(position)
        if not item:
            return
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu{{background-color:#0d001a;color:{CSS_PURPLE};border:1px solid {CSS_DPURPLE};}}"
            f"QMenu::item:selected{{background-color:#1a0035;}}"
        )
        rename_a = menu.addAction("Renomear")
        delete_a = menu.addAction("Apagar espaço")
        action = menu.exec(self.session_list.mapToGlobal(position))
        if action == rename_a:
            self._rename_session(item)
        elif action == delete_a:
            self._delete_session(item)

    def _rename_session(self, item):
        try:
            old = item.text()
            new_name, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=old)
            if ok and new_name.strip() and new_name != old:
                if get_luna()._memory.rename_session(old, new_name.strip()):
                    self._load()
        except Exception:
            pass

    def _delete_session(self, item):
        try:
            sid = item.text()
            reply = QMessageBox.question(
                self, "Apagar conversa",
                f"Apagar '{sid}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if get_luna()._memory.delete_session(sid):
                    self._load()
        except Exception:
            pass

    def _refresh(self):
        try:
            mem = get_luna()._memory
            self.chat_display.clear()
            for msg in mem.history:
                if msg["role"] == "user":
                    self.chat_display.append(
                        f"<p style='margin:4px 0;'>"
                        f"<span style='color:#7ec8e3;font-size:9pt;'>[você]</span>"
                        f"<br><span style='color:#ddeeff;font-size:11pt;'>{msg['text']}</span></p>"
                    )
                else:
                    self.chat_display.append(
                        f"<p style='margin:4px 0;'>"
                        f"<span style='color:{CSS_PURPLE};font-size:9pt;'>[luna]</span>"
                        f"<br><span style='color:#f0e8ff;font-size:11pt;'>{msg['text']}</span></p>"
                    )
            sb = self.chat_display.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass

    def _send(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_display.append(
            f"<p style='margin:4px 0;'>"
            f"<span style='color:#7ec8e3;font-size:9pt;'>[você]</span>"
            f"<br><span style='color:#ddeeff;font-size:11pt;'>{text}</span></p>"
        )
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum())
        self.worker.command_queue.append(("TEXT", text))
        self.chat_input.clear()

    def _on_chat(self, sender: str, text: str):
        if sender == "Luna":
            self.chat_display.append(
                f"<p style='margin:4px 0;'>"
                f"<span style='color:{CSS_PURPLE};font-size:9pt;'>[luna]</span>"
                f"<br><span style='color:#f0e8ff;font-size:11pt;'>{text}</span></p>"
            )
            self.chat_display.verticalScrollBar().setValue(
                self.chat_display.verticalScrollBar().maximum())

    def _on_status(self, status: str):
        dot = "●"
        if "PENSANDO" in status or "ESCREVENDO" in status:
            self.lbl_status.setText(f"{dot} pensando...")
            self.lbl_status.setStyleSheet("color:rgb(220,180,255);font-family:Ubuntu;font-size:7pt;")
        elif "FALANDO" in status:
            self.lbl_status.setText(f"{dot} falando...")
            self.lbl_status.setStyleSheet("color:rgb(255,220,255);font-family:Ubuntu;font-size:7pt;")
        elif "OUVINDO" in status:
            self.lbl_status.setText(f"{dot} ouvindo...")
            self.lbl_status.setStyleSheet("color:rgb(150,200,255);font-family:Ubuntu;font-size:7pt;")
        else:
            self.lbl_status.setText(f"{dot} modo papo ativo")
            self.lbl_status.setStyleSheet(f"color:{CSS_PURPLE};font-family:Ubuntu;font-size:7pt;")


# ══════════════════════════════════════════════════════════════
#  JANELA PRINCIPAL
# ══════════════════════════════════════════════════════════════

HUD_W      = 420
HUD_H      = 750
CHAT_W     = 460
WIDGET_W   = 240
ANIM_STEPS = 20


class LunaWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Luna")
        
        # Modo Agent X: Transparente, sem borda e por cima de tudo
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        central = QWidget()
        self._root_layout = QHBoxLayout(central)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self.setCentralWidget(central)

        # Área clicável transparente (Dim overlay)
        self.spacer = QWidget()
        self.spacer.setStyleSheet("background: transparent;")
        self.spacer.mousePressEvent = self._on_spacer_clicked
        self._root_layout.addWidget(self.spacer, stretch=1)

        # Container da Sidebar da Luna
        self.sidebar_container = QWidget()
        self.sidebar_container.setFixedWidth(460)
        self.sidebar_container.setStyleSheet("background-color: #080812; border-left: 1px solid rgba(255,255,255,10);")
        self.sidebar_layout = QVBoxLayout(self.sidebar_container)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        # Orb Console (Metade de cima)
        self.console = LunaConsoleWidget()
        self.console.setFixedHeight(320)
        self.console.input_box.hide() # Esconde o input antigo
        self.console.btn_clock.hide()

        # Chat Panel (Metade de baixo)
        self.chat_panel = LunaChatPanel(self.console.worker)
        self.chat_panel.btn_exit.hide()

        self.sidebar_layout.addWidget(self.console)
        self.sidebar_layout.addWidget(self.chat_panel)

        self._root_layout.addWidget(self.sidebar_container)

        self.console.setFocus()
        
        # Conecta o sinal de status para mostrar a UI automaticamente
        self.console.worker.status_signal.connect(self._on_worker_status)
        
        # Widget Manager
        self.console.wm = WidgetManager(self)
        self.console.worker.widget_signal.connect(self.console.wm.handle_widget_signal)

        # Oculta inicialmente
        self.hide()

    def paintEvent(self, event):
        # Escurece o fundo de toda a tela
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))

    def _on_spacer_clicked(self, event):
        # Fecha a UI se clicar fora da sidebar
        self.hide()

    def _on_worker_status(self, status: str):
        # Mostra o Agent X quando ativado
        if status in ["OUVINDO...", "PENSANDO...", "FALANDO..."]:
            if self.isHidden():
                self.showFullScreen()
                self.chat_panel._load()
                self.chat_panel.chat_input.setFocus()
        elif status == "SISTEMA ONLINE":
            # Poderia fechar, mas vamos deixar o usuário fechar clicando no fundo
            pass



    def closeEvent(self, event):
        self.console.worker.stop()
        self.console.worker.wait(2000)
        if hasattr(self.console, '_cava_proc') and self.console._cava_proc:
            self.console._cava_proc.kill()
            self.console._cava_proc.waitForFinished(1000)
        event.accept()


# ══════════════════════════════════════════════════════════════
#  LUNA WRITING PANEL
# ══════════════════════════════════════════════════════════════

WRITING_W = 560
_CSS_W = "background:#0a0010;color:#e8e0ff;font-family:'Ubuntu',monospace;font-size:11pt;border:none;padding:8px;"

class LunaWritingPanel(QWidget):
    """Editor Word-like com sugestões em tempo real da Luna."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:#08000f;")
        self._engine = None  # lazy
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.timeout.connect(self._request_suggestion)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("✍  LUNA WRITING")
        lbl.setFont(QFont("Ubuntu", 10, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#c8a0ff;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self.btn_fix = QPushButton("Corrigir")
        self.btn_sum = QPushButton("Resumir")
        self.btn_clear = QPushButton("Limpar")
        for btn, color in [(self.btn_fix, "#6030a0"), (self.btn_sum, "#304080"), (self.btn_clear, "#602020")]:
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f"QPushButton{{background:{color};color:#fff;border:none;border-radius:4px;"
                f"font-family:Ubuntu;font-size:8pt;padding:0 8px;}}"
                f"QPushButton:hover{{background:#ffffff;color:#000;}}"
            )
            hdr.addWidget(btn)

        self.btn_exit = QPushButton("✕")
        self.btn_exit.setFixedSize(22, 22)
        self.btn_exit.setStyleSheet(
            "QPushButton{background:transparent;color:#ff5555;border:none;font-size:13px;}"
            "QPushButton:hover{color:#ff8888;}"
        )
        hdr.addWidget(self.btn_exit)
        root.addLayout(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#2a0050;"); root.addWidget(sep)

        # Área principal de escrita
        self.editor = QTextEdit()
        self.editor.setStyleSheet(_CSS_W)
        self.editor.setPlaceholderText("Comece a escrever... Luna sugere em tempo real.")
        self.editor.textChanged.connect(self._on_text_changed)
        root.addWidget(self.editor, stretch=3)

        # Área de sugestão (read-only, estilo fantasma)
        lbl_sug = QLabel("💡 Sugestão Luna")
        lbl_sug.setStyleSheet("color:#6040a0;font-family:Ubuntu;font-size:8pt;")
        root.addWidget(lbl_sug)

        self.suggestion_box = QTextEdit()
        self.suggestion_box.setReadOnly(True)
        self.suggestion_box.setMaximumHeight(120)
        self.suggestion_box.setStyleSheet(
            "background:#050008;color:#8060c0;font-family:'Ubuntu',monospace;"
            "font-size:10pt;border:1px solid #2a0050;padding:6px;"
        )
        self.suggestion_box.setPlaceholderText("A sugestão aparece aqui...")
        root.addWidget(self.suggestion_box)

        # Botão aceitar sugestão
        self.btn_accept = QPushButton("↑ Aceitar sugestão  [Tab]")
        self.btn_accept.setFixedHeight(26)
        self.btn_accept.setStyleSheet(
            "QPushButton{background:#2a0060;color:#c8a0ff;border:1px solid #5030a0;"
            "border-radius:4px;font-family:Ubuntu;font-size:9pt;}"
            "QPushButton:hover{background:#5030a0;}"
        )
        self.btn_accept.clicked.connect(self._accept_suggestion)
        root.addWidget(self.btn_accept)

        self.btn_fix.clicked.connect(self._fix_text)
        self.btn_sum.clicked.connect(self._summarize)
        self.btn_clear.clicked.connect(self.editor.clear)

    @property
    def engine(self):
        if self._engine is None:
            from actions.writing import get_writing_engine
            self._engine = get_writing_engine()
        return self._engine

    def _on_text_changed(self):
        # Dispara sugestão 1.5s após parar de digitar
        self._suggest_timer.start(1500)

    def _request_suggestion(self):
        text = self.editor.toPlainText().strip()
        if len(text) < 20:
            return
        self.suggestion_box.setPlainText("...")

        def on_token(tok):
            cur = self.suggestion_box.toPlainText()
            self.suggestion_box.setPlainText(("" if cur == "..." else cur) + tok)

        def on_done(full):
            self.suggestion_box.setPlainText(full)

        self.engine.get_suggestion(text, on_token, on_done)

    def _accept_suggestion(self):
        sug = self.suggestion_box.toPlainText().strip()
        if sug and sug != "...":
            cur = self.editor.toPlainText()
            sep = "\n" if cur and not cur.endswith("\n") else ""
            self.editor.setPlainText(cur + sep + sug)
            self.suggestion_box.clear()
            # Move cursor para o fim
            cursor = self.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)

    def _fix_text(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self.suggestion_box.setPlainText("Corrigindo...")
        def _run():
            result = self.engine.fix_text(text)
            self.suggestion_box.setPlainText(result)
        threading.Thread(target=_run, daemon=True).start()

    def _summarize(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self.suggestion_box.setPlainText("Resumindo...")
        def _run():
            result = self.engine.summarize(text)
            self.suggestion_box.setPlainText(result)
        threading.Thread(target=_run, daemon=True).start()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Tab:
            self._accept_suggestion()
        else:
            super().keyPressEvent(e)


# ══════════════════════════════════════════════════════════════
#  LUNA MATH PANEL
# ══════════════════════════════════════════════════════════════

MATH_W = 520
_CSS_M = "background:#000a08;color:#00ffcc;font-family:'Ubuntu',monospace;font-size:11pt;border:none;padding:6px;"

class LunaMathPanel(QWidget):
    """Lousa digital matemática — escreve, avalia e pede ajuda à Luna."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:#000d0a;")
        self._board = None  # lazy
        self._strokes: list[list[tuple[int,int]]] = []   # traços do mouse
        self._current_stroke: list[tuple[int,int]] = []
        self._drawing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("🧮  LUNA MATH")
        lbl.setFont(QFont("Ubuntu", 10, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#00ffcc;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self.btn_clear_board = QPushButton("Limpar lousa")
        self.btn_clear_board.setFixedHeight(22)
        self.btn_clear_board.setStyleSheet(
            "QPushButton{background:#003020;color:#00ffcc;border:none;border-radius:4px;"
            "font-family:Ubuntu;font-size:8pt;padding:0 8px;}"
            "QPushButton:hover{background:#00ffcc;color:#000;}"
        )
        self.btn_clear_board.clicked.connect(self._clear_board)
        hdr.addWidget(self.btn_clear_board)

        self.btn_exit = QPushButton("✕")
        self.btn_exit.setFixedSize(22, 22)
        self.btn_exit.setStyleSheet(
            "QPushButton{background:transparent;color:#ff5555;border:none;font-size:13px;}"
            "QPushButton:hover{color:#ff8888;}"
        )
        hdr.addWidget(self.btn_exit)
        root.addLayout(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#003020;"); root.addWidget(sep)

        # Lousa (canvas de desenho)
        self.canvas = _MathCanvas(self)
        self.canvas.setMinimumHeight(200)
        root.addWidget(self.canvas, stretch=2)

        # Linha de expressão digitada
        expr_row = QHBoxLayout()
        self.expr_input = QLineEdit()
        self.expr_input.setPlaceholderText("Digite ou fale: 2^10 + 5 =")
        self.expr_input.setStyleSheet(
            "QLineEdit{background:#001a10;color:#00ffcc;border:1px solid #005040;"
            "border-radius:4px;font-family:Ubuntu;font-size:12pt;padding:6px;}"
            "QLineEdit:focus{border:1px solid #00ffcc;}"
        )
        self.expr_input.returnPressed.connect(self._evaluate)
        expr_row.addWidget(self.expr_input)

        self.btn_ia = QPushButton("🤖 IA")
        self.btn_ia.setFixedSize(52, 36)
        self.btn_ia.setToolTip("Luna completa o cálculo automaticamente")
        self.btn_ia.setStyleSheet(
            "QPushButton{background:#00ffcc;color:#000;border:none;border-radius:4px;"
            "font-family:Ubuntu;font-size:10pt;font-weight:bold;}"
            "QPushButton:hover{background:#ffffff;}"
        )
        self.btn_ia.clicked.connect(self._ia_complete)
        expr_row.addWidget(self.btn_ia)
        root.addLayout(expr_row)

        # Histórico de cálculos
        self.history_box = QTextEdit()
        self.history_box.setReadOnly(True)
        self.history_box.setMaximumHeight(110)
        self.history_box.setStyleSheet(
            "background:#000a08;color:#00cc99;font-family:'Ubuntu',monospace;"
            "font-size:10pt;border:1px solid #003020;padding:6px;"
        )
        self.history_box.setPlaceholderText("Histórico de cálculos...")
        root.addWidget(self.history_box)

        # Área de explicação da Luna
        lbl_exp = QLabel("💬 Luna explica")
        lbl_exp.setStyleSheet("color:#006050;font-family:Ubuntu;font-size:8pt;")
        root.addWidget(lbl_exp)

        self.explain_box = QTextEdit()
        self.explain_box.setReadOnly(True)
        self.explain_box.setMaximumHeight(100)
        self.explain_box.setStyleSheet(
            "background:#000d0a;color:#00aa88;font-family:'Ubuntu',monospace;"
            "font-size:9pt;border:1px solid #003020;padding:6px;"
        )
        self.explain_box.setPlaceholderText("Clique em 🤖 IA para Luna explicar o cálculo...")
        root.addWidget(self.explain_box)

    @property
    def board(self):
        if self._board is None:
            from actions.math_board import get_math_board
            self._board = get_math_board()
        return self._board

    def _evaluate(self):
        expr = self.expr_input.text().strip().rstrip("=").strip()
        if not expr:
            return
        result, ok = self.board.evaluate(expr)
        display = f"{expr} = {result}"
        self.expr_input.setText(display)
        self._append_history(display)
        if ok:
            self.explain_box.setPlainText("Clique em 🤖 IA para Luna explicar...")

    def _ia_complete(self):
        raw = self.expr_input.text().strip()
        # Extrai expressão antes do "=" se houver
        expr = raw.split("=")[0].strip()
        if not expr:
            # Pergunta em linguagem natural
            self.explain_box.setPlainText("Pensando...")
            def _run():
                answer = self.board.ask(raw)
                self.explain_box.setPlainText(answer)
            threading.Thread(target=_run, daemon=True).start()
            return

        result, ok = self.board.evaluate(expr)
        self.expr_input.setText(f"{expr} = {result}")
        self._append_history(f"{expr} = {result}")

        if ok:
            self.explain_box.setPlainText("Explicando...")
            def _run():
                explanation = self.board.explain(expr, result)
                self.explain_box.setPlainText(explanation)
            threading.Thread(target=_run, daemon=True).start()
        else:
            # Não é expressão numérica — pede ao LLM
            self.explain_box.setPlainText("Consultando Luna...")
            def _run():
                answer = self.board.ask(raw)
                self.explain_box.setPlainText(answer)
            threading.Thread(target=_run, daemon=True).start()

    def _append_history(self, line: str):
        cur = self.history_box.toPlainText()
        self.history_box.setPlainText((cur + "\n" if cur else "") + line)
        sb = self.history_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_board(self):
        self.canvas.clear()
        self.expr_input.clear()
        self.history_box.clear()
        self.explain_box.clear()
        self.board.clear()

    def set_expression(self, expr: str):
        """Chamado externamente (ex: por voz) para preencher a expressão."""
        self.expr_input.setText(expr)
        self._ia_complete()


class _MathCanvas(QWidget):
    """Canvas de desenho livre para a lousa matemática."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#001208;border:1px solid #003020;border-radius:4px;")
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._strokes: list[list[tuple[int,int]]] = []
        self._current: list[tuple[int,int]] = []
        self._drawing = False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._current = [(e.position().x(), e.position().y())]

    def mouseMoveEvent(self, e):
        if self._drawing:
            self._current.append((e.position().x(), e.position().y()))
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drawing and self._current:
            self._strokes.append(list(self._current))
            self._current = []
            self._drawing = False
            self.update()

    def clear(self):
        self._strokes.clear()
        self._current = []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 18, 8))
        pen = QPen(QColor(0, 255, 180, 220), 2, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for stroke in self._strokes:
            for i in range(1, len(stroke)):
                p.drawLine(int(stroke[i-1][0]), int(stroke[i-1][1]),
                           int(stroke[i][0]),   int(stroke[i][1]))
        # Traço atual
        for i in range(1, len(self._current)):
            p.drawLine(int(self._current[i-1][0]), int(self._current[i-1][1]),
                       int(self._current[i][0]),   int(self._current[i][1]))


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    start_server_thread()
    qt_app = QApplication(sys.argv)
    qt_app.setStyle("Fusion")
    window = LunaWindow()
    window.show()
    sys.exit(qt_app.exec())
