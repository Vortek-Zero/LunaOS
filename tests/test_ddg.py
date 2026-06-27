import urllib.request
import urllib.parse
import re

def _quick_search(query: str) -> str:
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)} pt-br"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            results = []
            for s in snippets[:3]:
                clean = re.sub(r'<[^>]+>', '', s)
                results.append(clean.strip())
            return " | ".join(results)
    except Exception as e:
        return f"Erro: {e}"

print(_quick_search("astronomia nebulosas planetárias"))
