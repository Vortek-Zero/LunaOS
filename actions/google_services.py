#!/usr/bin/env python3
"""
actions/google_services.py — Integração com Google Calendar e Gmail.

Requer o arquivo `credentials.json` (OAuth 2.0 Client IDs) baixado do Google Cloud Console
e salvo no diretório raiz do projeto (/home/pera/Luna/credentials.json).
Na primeira execução, abrirá o navegador para autorizar e salvará `token.json`.
"""
import os
import datetime
from pathlib import Path
from typing import Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/gmail.readonly'
]

BASE_DIR = Path(__file__).parent.parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


class GoogleManager:
    def __init__(self):
        self.creds = None
        self.available = False
        
        if not HAS_GOOGLE:
            print("[Google] ⚠ Bibliotecas não instaladas. (pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib)")
            return

        if not CREDENTIALS_FILE.exists():
            print(f"[Google] ⚠ credentials.json não encontrado. Google Calendar/Gmail desabilitados.")
            return

        self._authenticate()

    def _authenticate(self):
        try:
            if TOKEN_FILE.exists():
                self.creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    print("[Google] 🌐 Abrindo navegador para autorização OAuth...")
                    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
                    self.creds = flow.run_local_server(port=0)
                TOKEN_FILE.write_text(self.creds.to_json(), encoding="utf-8")
            self.available = True
            print("[Google] ✓ Autenticado com sucesso no Google Calendar e Gmail.")
        except Exception as e:
            print(f"[Google] ⚠ Erro de autenticação: {e}")
            self.available = False

    def get_calendar_events(self, max_results: int = 5) -> str:
        if not self.available:
            return "Google Calendar não configurado. Adicione credentials.json na pasta do projeto."
        
        try:
            service = build("calendar", "v3", credentials=self.creds)
            now = datetime.datetime.utcnow().isoformat() + "Z"
            
            print("[Google] Buscando próximos eventos no calendário...")
            events_result = service.events().list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            
            events = events_result.get("items", [])
            
            if not events:
                return "Não há compromissos próximos no seu calendário."
                
            response = ["📅 Seus próximos compromissos:"]
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                try:
                    dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    time_str = dt.strftime("%d/%m %H:%M")
                except Exception:
                    time_str = start
                
                response.append(f"  • {time_str} - {event['summary']}")
                
            return "\n".join(response)

        except HttpError as error:
            return f"Ocorreu um erro ao acessar o calendário: {error}"
        except Exception as e:
            return f"Erro inesperado no calendário: {e}"

    def get_unread_emails(self, max_results: int = 5) -> str:
        if not self.available:
            return "Gmail não configurado. Adicione credentials.json na pasta do projeto."
            
        try:
            service = build("gmail", "v1", credentials=self.creds)
            
            print("[Google] Buscando emails não lidos...")
            results = service.users().messages().list(
                userId="me", 
                labelIds=["INBOX", "UNREAD"],
                maxResults=max_results
            ).execute()
            
            messages = results.get("messages", [])
            
            if not messages:
                return "Você não tem emails não lidos importantes no momento."
                
            response = [f"📧 Você tem {len(messages)} (ou mais) emails não lidos. Aqui estão os últimos:"]
            
            for msg in messages:
                msg_data = service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata", 
                    metadataHeaders=["Subject", "From"]
                ).execute()
                
                headers = msg_data.get("payload", {}).get("headers", [])
                subject = "Sem Assunto"
                sender = "Desconhecido"
                
                for header in headers:
                    if header["name"] == "Subject":
                        subject = header["value"]
                    elif header["name"] == "From":
                        sender = header["value"]
                        import re
                        m = re.search(r'([^<]+)', sender)
                        if m:
                            sender = m.group(1).strip()
                
                response.append(f"  • De {sender}: {subject}")
                
            return "\n".join(response)

        except HttpError as error:
            return f"Ocorreu um erro ao acessar o Gmail: {error}"
        except Exception as e:
            return f"Erro inesperado no Gmail: {e}"

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()
        
        # Calendar
        if any(w in tl for w in ["compromisso", "compromissos", "calendário", "calendario", "agenda", "reunião", "reuniao"]):
            return self.get_calendar_events()
            
        # Gmail
        if any(w in tl for w in ["email", "emails", "e-mail", "e-mails"]):
            return self.get_unread_emails()
            
        return None

# Singleton
_google_instance: Optional[GoogleManager] = None

def get_google() -> GoogleManager:
    global _google_instance
    if _google_instance is None:
        _google_instance = GoogleManager()
    return _google_instance
