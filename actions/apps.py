import subprocess
import shutil
import json
from pathlib import Path
from typing import Optional

APPS_FILE = Path(__file__).parent.parent / "config" / "apps.json"

class AppManager:
    """Gerencia listagem e execução de aplicações locais."""
    
    def __init__(self):
        self.apps: dict = self._load_apps()
        if not self.apps:
            self._discover_apps()
            
    def _load_apps(self) -> dict:
        try:
            if APPS_FILE.exists():
                return json.loads(APPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_apps(self) -> None:
        try:
            APPS_FILE.write_text(
                json.dumps(self.apps, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _discover_apps(self) -> None:
        binaries = [
            "firefox", "chromium", "chrome", "code", "gedit", "nautilus",
            "gnome-terminal", "vlc", "spotify", "telegram-desktop", "obs",
            "gimp", "blender", "thunderbird", "libreoffice",
        ]
        for name in binaries:
            path = shutil.which(name)
            if path:
                self.apps[name] = {
                    "command": path,
                    "description": f"{name} (detectado automaticamente)",
                    "enabled": True,
                }
        for dp in [
            Path.home() / ".local/share/applications",
            Path("/usr/share/applications"),
        ]:
            if not dp.exists():
                continue
            for f in dp.glob("*.desktop"):
                try:
                    content = f.read_text(errors="ignore")
                    name = f.stem.lower()
                    for line in content.split("\n"):
                        if line.startswith("Exec="):
                            cmd = line.split("=", 1)[1].split("%")[0].strip()
                            if name not in self.apps and cmd:
                                self.apps[name] = {
                                    "command": cmd,
                                    "description": f"{name} (desktop)",
                                    "enabled": True,
                                }
                            break
                except Exception:
                    pass
        if self.apps:
            self._save_apps()

    def open_app(self, name: str) -> dict:
        name = name.lower().strip()
        app = self.apps.get(name)
        if not app:
            for key, val in self.apps.items():
                if name in key or key in name:
                    app = val
                    name = key
                    break

        if not app:
            return {"success": False, "message": f"App '{name}' não encontrado."}
        if not app.get("enabled", True):
            return {"success": False, "message": f"App '{name}' está desativado."}

        try:
            from actions.gnome import launch_app
            cmd = app["command"]
            ok, msg = launch_app(name, fallback_cmd=cmd)
            if ok:
                print(f"[AppManager] {msg} (cmd: {cmd})")
                return {"success": True, "message": msg}
            print(f"[AppManager] Abrindo: {cmd}")
            subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return {"success": True, "message": f"Abrindo {name}"}
        except Exception as e:
            return {"success": False, "message": f"Erro ao abrir {name}: {e}"}

    def get_app_names(self) -> list[str]:
        return [k for k, v in self.apps.items() if v.get("enabled", True)]

    def find_best_app(self, query: str) -> Optional[str]:
        q = query.lower().strip()
        if q in self.apps:
            return q
        for name in self.apps:
            if name.startswith(q) or q.startswith(name):
                return name
        for name in self.apps:
            if q in name or name in q:
                return name
        return None
