#!/usr/bin/env python3
"""
actions/gnome.py — Integração com GNOME no Arch Linux.

- Abre apps via gio launch (.desktop) — forma nativa do GNOME
- Terminal padrão do sistema (gsettings) com zsh
- Fallback para subprocess quando gio não estiver disponível
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

DESKTOP_DIRS = (
    Path.home() / ".local/share/applications",
    Path("/usr/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
)

DESKTOP_ALIASES: dict[str, list[str]] = {
    "firefox": ["firefox.desktop", "org.mozilla.firefox.desktop"],
    "nautilus": ["org.gnome.Nautilus.desktop"],
    "arquivos": ["org.gnome.Nautilus.desktop"],
    "files": ["org.gnome.Nautilus.desktop"],
    "terminal": ["org.gnome.Terminal.desktop"],
    "gnome-terminal": ["org.gnome.Terminal.desktop"],
    "calculadora": ["org.gnome.Calculator.desktop"],
    "ajustes": ["org.gnome.Settings.desktop"],
    "settings": ["org.gnome.Settings.desktop"],
    "code": ["code.desktop", "code-oss.desktop", "visual studio code.desktop"],
    "vscode": ["code.desktop", "code-oss.desktop"],
    "spotify": ["spotify.desktop", "com.spotify.Client.desktop"],
    "telegram": ["org.telegram.desktop", "telegram-desktop.desktop"],
    "discord": ["discord.desktop", "discord-canary.desktop"],
    "thunderbird": ["org.mozilla.thunderbird.desktop", "thunderbird.desktop"],
    "whatsapp": ["whatsapp.desktop", "io.github.mimbrero.WhatsAppDesktop.desktop"],
}


def _gsettings_get(schema: str, key: str) -> str:
    if not shutil.which("gsettings"):
        return ""
    try:
        r = subprocess.run(
            ["gsettings", "get", schema, key],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            return r.stdout.strip().strip("'\"")
    except Exception:
        pass
    return ""


def get_default_terminal() -> str:
    """Terminal padrão do GNOME (org.gnome.desktop.default-applications.terminal)."""
    exec_arg = _gsettings_get("org.gnome.desktop.default-applications.terminal", "exec")
    if exec_arg:
        candidate = exec_arg.split()[0]
        if shutil.which(candidate):
            return candidate
    for candidate in ("gnome-terminal", "xdg-terminal-exec", "kgx", "kitty", "alacritty", "xterm"):
        if shutil.which(candidate):
            return candidate
    return "xterm"


def _desktop_paths() -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for d in DESKTOP_DIRS:
        if not d.exists():
            continue
        for f in d.glob("*.desktop"):
            key = f.name.lower()
            if key not in seen:
                seen.add(key)
                found.append(f)
    return found


def find_desktop_file(name: str) -> Optional[str]:
    """Resolve nome fuzzy → caminho absoluto do .desktop."""
    q = name.lower().strip().replace("_", "-")
    aliases = DESKTOP_ALIASES.get(q, [])
    desktops = _desktop_paths()

    for alias in aliases:
        for f in desktops:
            if f.name.lower() == alias.lower():
                return str(f)

    for f in desktops:
        stem = f.stem.lower()
        if q == stem or q in stem or stem in q:
            return str(f)

    q_compact = q.replace(" ", "")
    for f in desktops:
        stem = f.stem.lower().replace(" ", "")
        if q_compact in stem or stem in q_compact:
            return str(f)
    return None


def gio_launch(desktop_path: str) -> bool:
    if not shutil.which("gio"):
        return False
    try:
        subprocess.Popen(
            ["gio", "launch", desktop_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ},
        )
        return True
    except Exception:
        return False


def launch_app(name: str, fallback_cmd: str = "") -> tuple[bool, str]:
    """Abre app pelo GNOME (gio) ou comando fallback."""
    desktop = find_desktop_file(name)
    if desktop and gio_launch(desktop):
        label = Path(desktop).stem
        return True, f"Abrindo {label} (GNOME)"

    if fallback_cmd:
        try:
            subprocess.Popen(
                fallback_cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={**os.environ},
            )
            return True, f"Abrindo {name}"
        except Exception as e:
            return False, f"Erro ao abrir {name}: {e}"

    return False, f"App '{name}' não encontrado."


def open_terminal_zsh(command: str, title: str = "Luna", cwd: Optional[str] = None) -> str:
    """
    Abre terminal visível com zsh e executar comando.
    O usuário vê a saída no GNOME Terminal (ou terminal padrão).
    """
    cmd_clean = (command or "").strip()
    if not cmd_clean:
        return "FALHOU: comando vazio."

    workdir = str(Path(cwd or Path.home()).expanduser())
    term = get_default_terminal()
    safe_title = title[:60].replace("'", "")

    try:
        if term.endswith("gnome-terminal") or term == "gnome-terminal":
            subprocess.Popen(
                [
                    "gnome-terminal",
                    f"--title={safe_title}",
                    f"--working-directory={workdir}",
                    "--",
                    "zsh", "-lc",
                    f"{cmd_clean}; echo; echo '[Luna] Comando concluído.'; exec zsh -i",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ},
            )
        elif "xdg-terminal-exec" in term or term.endswith("xdg-terminal-exec"):
            subprocess.Popen(
                [
                    term if shutil.which(term) else "xdg-terminal-exec",
                    "--working-directory", workdir,
                    "--title", safe_title,
                    "--", "zsh", "-lc",
                    f"{cmd_clean}; echo; echo '[Luna] Comando concluído.'; exec zsh -i",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ},
            )
        elif term == "kitty":
            subprocess.Popen(
                ["kitty", "--directory", workdir, "zsh", "-lc",
                 f"{cmd_clean}; echo; echo '[Luna] Comando concluído.'; exec zsh -i"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ},
            )
        elif term == "kgx":
            subprocess.Popen(
                ["kgx", "--", "zsh", "-lc",
                 f"cd {workdir}; {cmd_clean}; echo; echo '[Luna] Comando concluído.'; exec zsh -i"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ},
            )
        else:
            subprocess.Popen(
                [term, "-e", "zsh", "-lc",
                 f"cd {workdir}; {cmd_clean}; echo; read -p 'Enter para fechar...'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ},
            )
        return f"Terminal aberto ({term}): {cmd_clean[:120]}"
    except Exception as e:
        return f"FALHOU: não abri terminal — {e}"


def open_terminal_shell(title: str = "Luna — Terminal") -> str:
    """Abre um terminal zsh vazio para a Luna usar depois."""
    return open_terminal_zsh("echo 'Terminal Luna pronto.'", title=title)
