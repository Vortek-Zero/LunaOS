import contextlib
import json
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from version import __repo__, __version__


def _parse_version(v: str) -> tuple[int, ...]:
    v = v.lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def get_latest_github_version() -> str | None:
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


def check_for_update() -> str | None:
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
        with contextlib.suppress(subprocess.SubprocessError):
            subprocess.run(["notify-send", "-u", "normal", "-t", "10000", title, message], check=True, timeout=5)
    print(f"\n[Updater] {title}")
    print(f"[Updater] {message}\n")


def check_and_notify() -> None:
    new_ver = check_for_update()
    if new_ver:
        notify_update(new_ver)


def run_update_check() -> None:
    thread = threading.Thread(target=check_and_notify, daemon=True)
    thread.start()


def _get_repo_root() -> str:
    return str(Path(__file__).resolve().parent.parent)


def _get_tracking_remote() -> str | None:
    """Descobre a remote associada ao branch atual."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if not branch:
            return None
        remote = subprocess.run(
            ["git", "config", f"branch.{branch}.remote"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return remote if remote and remote != "." else None
    except Exception:
        return None


def perform_update() -> str:
    """Executa git pull para atualizar o repositório."""
    repo_root = _get_repo_root()
    git_dir = str(Path(repo_root) / ".git")
    remote = _get_tracking_remote()
    if not remote:
        remote = "origin"
    try:
        subprocess.run(
            ["git", "--git-dir", git_dir, "--work-tree", repo_root, "fetch", remote],
            capture_output=True,
            timeout=30,
        )
        result = subprocess.run(
            ["git", "--git-dir", git_dir, "--work-tree", repo_root, "pull", remote, "main"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if "Already up to date" in output:
                return f"Luna já está atualizada (v{__version__})."
            return f"Luna atualizada com sucesso!\n{output}"
        return f"Falha ao atualizar: {result.stderr.strip()}"
    except Exception as e:
        return f"Erro ao atualizar: {e}"


def test_notification() -> str:
    notify_update(f"TESTE ({__version__})")
    return f"Notificação de teste enviada (versão atual: {__version__})"


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        print(test_notification())
    else:
        check_and_notify()
