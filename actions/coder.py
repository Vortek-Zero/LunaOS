import os
from pathlib import Path

from config import WORKSPACE_DIR

class CoderManager:
    """Gerencia a criação e modificação de código pela IA na sua pasta de trabalho."""

    def __init__(self):
        # A pasta dedicada para o código gerado pela Luna
        self.workspace = WORKSPACE_DIR
        self.workspace.mkdir(parents=True, exist_ok=True)

    def write_code(self, filename: str, content: str) -> dict:
        """Escreve código em um arquivo dentro do workspace."""
        if not filename:
            return {"success": False, "message": "Nome do arquivo não fornecido."}
        
        # Sanitizar nome de arquivo para evitar path traversal
        clean_filename = Path(filename).name
        filepath = self.workspace / clean_filename

        try:
            filepath.write_text(content, encoding="utf-8")
            print(f"[CoderManager] Arquivo salvo em: {filepath}")
            return {"success": True, "message": f"Código escrito com sucesso no arquivo '{clean_filename}' localizado na pasta 'Luna-programming'."}
        except Exception as e:
            return {"success": False, "message": f"Erro ao escrever arquivo: {e}"}

    def _open_file_for_stream(self, filename: str):
        """Retorna o file handle para escrita contínua. Feche depois."""
        clean_filename = Path(filename).name
        filepath = self.workspace / clean_filename
        return open(filepath, "w", encoding="utf-8"), filepath
