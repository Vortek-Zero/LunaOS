import json
import subprocess
import shutil
import threading
from urllib.request import urlopen, Request
from urllib.error import URLError
from typing import Optional, Tuple

from version import __version__, __repo__


def _parse_version(v: str) -> Tuple[int, ...]:
    v = v.lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def get_latest_github_version() -> Optional[str]:
    url = f"https://api.github.com/repos/{__repo__}/releases/latest"
    try:
        req = Request(url, headers={"User-Agent": "LunaOS/updater", "Accept": "application/vnd.github.v3+json"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("tag_name") or data.get("name")
    except (URLError, json.JSONDecodeError, KeyError):
        try:
            alt_url = f"https://api.github.com/repos/{__repo__}/tags"
            req = Request(alt_url, headers={"User-Agent": "LunaOS/updater", "Accept": "application/vnd.github.v3+json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data and isinstance(data, list):
                    return data[0].get("name")
        except (URLError, json.JSONDecodeError, KeyError, IndexError):
            pass
    return None


def check_for_update() -> Optional[str]:
    latest_tag = get_latest_github_version()
    if latest_tag is None:
        return None

    latest_ver = _parse_version(latest_tag)
    current_ver = _parse_version(__version__)

    if latest_ver > current_ver:
        return latest_tag
    return None


def notify_update(new_version: str) -> None:
    title = "LunaOS — Atualização Disponível"
    message = f"Versão {new_version} disponível (atual: {__version__}).\nGostaria de atualizar?"
    if shutil.which("notify-send"):
        try:
            subprocess.run(
                ["notify-send", "-u", "normal", "-t", "10000", title, message],
                check=True, timeout=5
            )
        except subprocess.SubprocessError:
            pass
    print(f"\n[Updater] {title}")
    print(f"[Updater] {message}\n")


def check_and_notify() -> None:
    new_ver = check_for_update()
    if new_ver:
        notify_update(new_ver)


def run_update_check() -> None:
    thread = threading.Thread(target=check_and_notify, daemon=True)
    thread.start()


def test_notification() -> str:
    notify_update(f"TESTE ({__version__})")
    return f"Notificação de teste enviada (versão atual: {__version__})"


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        print(test_notification())
    else:
        check_and_notify()
