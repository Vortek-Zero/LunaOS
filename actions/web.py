import subprocess
import shutil
import webbrowser
from urllib.parse import quote
from actions.apps import AppManager

class WebManager:
    """Gerencia a abertura de URLs e navegação na web."""

    def __init__(self, app_manager: AppManager):
        self.app_manager = app_manager
        self.last_search_query: str = ""

    def open_url(self, url: str, browser: str = "firefox") -> dict:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            browser_cmd = self.app_manager.apps.get(browser.lower(), {}).get("command")
            if browser_cmd:
                subprocess.Popen(
                    f"{browser_cmd} '{url}'", shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif shutil.which("xdg-open"):
                subprocess.Popen(
                    ["xdg-open", url],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                webbrowser.open(url)
            print(f"[WebManager] Abrindo URL: {url}")
            return {"success": True, "message": f"Abrindo {url}"}
        except Exception as e:
            return {"success": False, "message": f"Erro ao abrir URL: {e}"}

    def search_web(self, query: str, browser: str = "firefox") -> dict:
        self.last_search_query = query.strip()
        url = f"https://www.google.com/search?q={quote(query)}"
        print(f"[WebManager] Pesquisando: {query}")
        return self.open_url(url, browser)

    def open_search_result(self, index: int = 0, query: str = "") -> dict:
        """Abre o N-ésimo resultado da última busca (ou query informada)."""
        from actions.web_nav import fetch_first_result_url
        q = (query or self.last_search_query).strip()
        if not q:
            return {"success": False, "message": "FALHOU: nenhuma pesquisa recente. Diga o que buscar primeiro."}
        url = fetch_first_result_url(q, index=index)
        if not url:
            return {"success": False, "message": f"FALHOU: não achei o {index + 1}º resultado para '{q}'."}
        return self.open_url(url)

    def read_page(self, url: str) -> str:
        """Lê o conteúdo limpo de uma URL usando a Jina Reader API (Markdown puro)."""
        import urllib.request
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            
        jina_url = f"https://r.jina.ai/{url}"
        print(f"[WebManager] Lendo página via Jina AI: {url}")
        try:
            req = urllib.request.Request(
                jina_url, 
                headers={'User-Agent': 'LunaAI/1.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')
                return content
        except Exception as e:
            print(f"[WebManager] Erro ao ler página com Jina AI: {e}")
            return f"Não foi possível ler o site. Erro: {str(e)}"
