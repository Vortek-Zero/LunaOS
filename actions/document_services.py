#!/usr/bin/env python3
"""
actions/document_services.py — Manipulação de documentos, planilhas e arquivos.
Suporta criação de planilhas Excel, exportação de PDF via Google Drive, e leitura/escrita de arquivos locais.
"""
import os
import io
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from actions.google_services import get_google
from config import WORKSPACE_DIR

class DocumentServices:
    """Serviços de documentos locais e integração com Google Drive."""

    def __init__(self):
        pass

    def _resolve_path(self, filepath_or_name: str) -> Path:
        """Resolve caminhos garantindo que fiquem dentro do workspace de programação ou home."""
        path = Path(filepath_or_name)
        if not path.is_absolute():
            path = WORKSPACE_DIR / path
        # Segurança: impede sair do workspace ou do diretório home do usuário
        resolved = path.resolve()
        home = Path.home()
        if not (resolved.is_relative_to(WORKSPACE_DIR) or resolved.is_relative_to(home)):
            raise PermissionError("Acesso não autorizado fora do workspace de programação ou diretório home.")
        return resolved

    def create_excel(self, data: List[Dict[str, Any]], filename: str) -> str:
        """
        Cria uma planilha Excel (.xlsx) a partir de uma lista de dicionários.
        Salva no workspace Luna-programming.
        """
        try:
            if not filename.endswith(".xlsx"):
                filename += ".xlsx"
            path = self._resolve_path(filename)
            
            # Converte dados para DataFrame do Pandas e salva via openpyxl
            df = pd.DataFrame(data)
            df.to_excel(str(path), index=False, engine='openpyxl')
            
            return f"Planilha Excel criada com sucesso em: {path.name}"
        except Exception as e:
            return f"FALHOU: Erro ao criar planilha Excel: {str(e)}"

    def create_pdf_drive(self, content: str, title: str) -> str:
        """
        Cria um documento PDF exportado via Google Drive API a partir de texto.
        Gera um arquivo PDF no workspace local e faz upload/compartilhamento no Drive.
        """
        g = get_google()
        if not g or not g.available:
            return "FALHOU: Google API não está disponível para gerar o PDF."
        
        try:
            # 1. Cria um Google Doc temporário a partir do conteúdo de texto
            from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
            drive_service = g._drive()
            
            file_metadata = {
                'name': title,
                'mimeType': 'application/vnd.google-apps.document'
            }
            media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain', resumable=True)
            doc = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            doc_id = doc.get('id')
            
            # 2. Exporta o Google Doc como PDF em memória
            request = drive_service.files().export_media(fileId=doc_id, mimeType='application/pdf')
            pdf_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(pdf_buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            # 3. Salva o PDF localmente no workspace
            pdf_filename = f"{title.replace(' ', '_')}.pdf"
            pdf_path = self._resolve_path(pdf_filename)
            pdf_path.write_bytes(pdf_buffer.getvalue())
            
            # 4. Remove o Google Doc temporário do Drive
            drive_service.files().delete(fileId=doc_id).execute()
            
            # 5. Sobe o arquivo PDF final de volta para o Drive para obter o link público
            res_upload = g.google_drive_upload(str(pdf_path))
            
            return f"PDF '{pdf_filename}' criado e salvo localmente. {res_upload}"
        except Exception as e:
            return f"FALHOU: Erro ao gerar o PDF via Google Drive: {str(e)}"

    def read_file(self, filepath_or_name: str) -> str:
        """
        Lê e extrai texto de arquivos locais (.txt, .csv, .xlsx, .pdf).
        """
        try:
            path = self._resolve_path(filepath_or_name)
            if not path.exists():
                return f"FALHOU: Arquivo não existe: {filepath_or_name}"
            
            ext = path.suffix.lower()
            
            if ext == ".txt":
                return path.read_text(encoding="utf-8")
                
            elif ext == ".csv":
                with open(path, mode='r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    lines = [",".join(row) for row in reader]
                return "\n".join(lines[:100])  # limita a 100 linhas para evitar estouro de contexto
                
            elif ext == ".xlsx":
                df = pd.read_excel(str(path), engine='openpyxl')
                return df.to_string(index=False)
                
            elif ext == ".pdf":
                import pdfplumber
                text_content = []
                with pdfplumber.open(str(path)) as pdf:
                    for i, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        if text:
                            text_content.append(f"--- Página {i+1} ---\n{text}")
                if not text_content:
                    return "FALHOU: Não foi possível extrair texto do PDF (pode ser escaneado/imagem)."
                return "\n\n".join(text_content)
                
            else:
                return f"FALHOU: Extensão de arquivo não suportada para leitura direta: {ext}"
        except Exception as e:
            return f"FALHOU: Erro ao ler arquivo: {str(e)}"

    def save_file(self, content: str, filepath_or_name: str) -> str:
        """
        Salva texto em um arquivo local no workspace.
        """
        try:
            path = self._resolve_path(filepath_or_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Arquivo salvo com sucesso em: {path.name}"
        except Exception as e:
            return f"FALHOU: Erro ao salvar arquivo: {str(e)}"


# Singleton helper
_doc_services_instance = None

def get_doc_services() -> DocumentServices:
    global _doc_services_instance
    if _doc_services_instance is None:
        _doc_services_instance = DocumentServices()
    return _doc_services_instance
