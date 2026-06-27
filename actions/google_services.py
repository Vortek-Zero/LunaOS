#!/usr/bin/env python3
"""
actions/google_services.py — Integração COMPLETA com Google Calendar e Gmail.

Capacidades COMPLETAS:
  Calendar: ler, criar, editar, deletar eventos, buscar por data
  Gmail: ler, enviar, enviar com anexo, responder, encaminhar, buscar, deletar, marcar lido
"""
import os
import re
import base64
import datetime
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional, List

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

# Escopos completos — leitura E escrita
SCOPES = [
    'https://www.googleapis.com/auth/calendar',        # Calendar full
    'https://www.googleapis.com/auth/gmail.modify',     # Gmail modify
    'https://www.googleapis.com/auth/gmail.send',       # Gmail send
    'https://www.googleapis.com/auth/drive',            # Drive full (leitura, escrita, exclusão)
]

BASE_DIR = Path(__file__).parent.parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
from config import WORKSPACE_DIR

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

    def _cal(self):
        return build("calendar", "v3", credentials=self.creds)

    def _gmail(self):
        return build("gmail", "v1", credentials=self.creds)

    def _drive(self):
        return build("drive", "v3", credentials=self.creds)

    # ══════════════════════════════════════════════════════════════
    #                     GOOGLE CALENDAR
    # ══════════════════════════════════════════════════════════════

    # ── Ler eventos ───────────────────────────────────────────────

    def get_calendar_events(self, max_results: int = 10) -> str:
        """Lista os próximos eventos do calendário."""
        if not self.available:
            return "Google Calendar não configurado."
        try:
            service = self._cal()
            now = datetime.datetime.utcnow().isoformat() + "Z"
            events_result = service.events().list(
                calendarId="primary", timeMin=now,
                maxResults=max_results, singleEvents=True, orderBy="startTime"
            ).execute()
            events = events_result.get("items", [])
            if not events:
                return "Não há compromissos próximos no seu calendário."
            lines = ["📅 Seus próximos compromissos:"]
            for ev in events:
                start = ev["start"].get("dateTime", ev["start"].get("date"))
                try:
                    dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    t = dt.strftime("%d/%m %H:%M")
                except Exception:
                    t = start
                lines.append(f"  • {t} - {ev['summary']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao acessar o calendário: {e}"

    def get_today_events_formatted(self) -> str:
        """Retorna eventos de hoje em formato conciso para o briefing."""
        if not self.available:
            return ""
        try:
            service = self._cal()
            today = datetime.date.today().isoformat()
            time_min = today + "T00:00:00Z"
            time_max = today + "T23:59:59Z"
            events = service.events().list(
                calendarId="primary", timeMin=time_min, timeMax=time_max,
                maxResults=15, singleEvents=True, orderBy="startTime"
            ).execute().get("items", [])
            if not events:
                return ""
            lines = []
            for ev in events:
                start = ev["start"].get("dateTime", ev["start"].get("date"))
                try:
                    t = datetime.datetime.fromisoformat(start.replace('Z', '+00:00')).strftime("%H:%M")
                except Exception:
                    t = "Dia inteiro"
                lines.append(f"  • {t} — {ev['summary']}")
            return "\n".join(lines)
        except Exception:
            return ""

    def get_events_by_date(self, date_str: str, max_results: int = 20) -> str:
        """Lista eventos de uma data específica (YYYY-MM-DD)."""
        if not self.available:
            return "Google Calendar não configurado."
        try:
            service = self._cal()
            dt = datetime.datetime.fromisoformat(date_str)
            time_min = dt.replace(hour=0, minute=0, second=0).isoformat() + "Z"
            time_max = dt.replace(hour=23, minute=59, second=59).isoformat() + "Z"
            result = service.events().list(
                calendarId="primary", timeMin=time_min, timeMax=time_max,
                maxResults=max_results, singleEvents=True, orderBy="startTime"
            ).execute()
            events = result.get("items", [])
            if not events:
                return f"Nenhum compromisso encontrado para {date_str}."
            lines = [f"📅 Compromissos em {date_str}:"]
            for ev in events:
                start = ev["start"].get("dateTime", ev["start"].get("date"))
                try:
                    t = datetime.datetime.fromisoformat(start.replace('Z', '+00:00')).strftime("%H:%M")
                except Exception:
                    t = "Dia inteiro"
                lines.append(f"  • {t} - {ev['summary']} (ID: {ev['id'][:8]})")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao buscar eventos por data: {e}"

    # ── Criar evento ──────────────────────────────────────────────

    def create_calendar_event(self, summary: str, start_time: str, end_time: str = None,
                               description: str = "", location: str = "",
                               attendees: str = "") -> str:
        """Cria um evento. attendees = emails separados por vírgula."""
        if not self.available:
            return "Google Calendar não configurado."
        try:
            service = self._cal()
            is_all_day = len(start_time) <= 10
            if is_all_day:
                body = {
                    "summary": summary,
                    "start": {"date": start_time},
                    "end": {"date": end_time or start_time},
                }
            else:
                if not end_time:
                    try:
                        dt_s = datetime.datetime.fromisoformat(start_time)
                        end_time = (dt_s + datetime.timedelta(hours=1)).isoformat()
                    except Exception:
                        end_time = start_time
                body = {
                    "summary": summary,
                    "start": {"dateTime": start_time, "timeZone": "America/Sao_Paulo"},
                    "end": {"dateTime": end_time, "timeZone": "America/Sao_Paulo"},
                }
            if description:
                body["description"] = description
            if location:
                body["location"] = location
            if attendees:
                body["attendees"] = [{"email": e.strip()} for e in attendees.split(",") if e.strip()]
            print(f"[Google] Criando evento: {summary}")
            ev = service.events().insert(calendarId="primary", body=body).execute()
            return f"✅ Evento criado: '{summary}'\n🔗 Link: {ev.get('htmlLink', 'N/A')}"
        except Exception as e:
            return f"Erro ao criar evento: {e}"

    # ── Editar evento ─────────────────────────────────────────────

    def edit_calendar_event(self, event_id: str, summary: str = None,
                             start_time: str = None, end_time: str = None,
                             description: str = None, location: str = None) -> str:
        """Edita campos de um evento existente pelo ID."""
        if not self.available:
            return "Google Calendar não configurado."
        try:
            service = self._cal()
            ev = service.events().get(calendarId="primary", eventId=event_id).execute()
            if summary:
                ev["summary"] = summary
            if description is not None:
                ev["description"] = description
            if location is not None:
                ev["location"] = location
            if start_time:
                if len(start_time) <= 10:
                    ev["start"] = {"date": start_time}
                else:
                    ev["start"] = {"dateTime": start_time, "timeZone": "America/Sao_Paulo"}
            if end_time:
                if len(end_time) <= 10:
                    ev["end"] = {"date": end_time}
                else:
                    ev["end"] = {"dateTime": end_time, "timeZone": "America/Sao_Paulo"}
            updated = service.events().update(calendarId="primary", eventId=event_id, body=ev).execute()
            return f"✅ Evento atualizado: '{updated.get('summary')}'"
        except Exception as e:
            return f"Erro ao editar evento: {e}"

    # ── Deletar evento ────────────────────────────────────────────

    def delete_calendar_event(self, event_id: str) -> str:
        """Deleta um evento pelo ID."""
        if not self.available:
            return "Google Calendar não configurado."
        try:
            service = self._cal()
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return f"✅ Evento deletado com sucesso (ID: {event_id[:8]}…)"
        except Exception as e:
            return f"Erro ao deletar evento: {e}"

    # ══════════════════════════════════════════════════════════════
    #                          GMAIL
    # ══════════════════════════════════════════════════════════════

    # ── Ler emails não lidos ──────────────────────────────────────

    def get_unread_emails(self, max_results: int = 5) -> str:
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            results = service.users().messages().list(
                userId="me", labelIds=["INBOX", "UNREAD"], maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return "Você não tem emails não lidos no momento."
            lines = [f"📧 {len(messages)} emails não lidos:"]
            for msg in messages:
                meta = service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ).execute()
                headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
                sender = headers.get("From", "Desconhecido")
                m = re.search(r'([^<]+)', sender)
                if m:
                    sender = m.group(1).strip()
                lines.append(f"  • De {sender}: {headers.get('Subject', 'Sem Assunto')} (ID: {msg['id'][:8]})")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao acessar o Gmail: {e}"

    # ── Buscar emails ─────────────────────────────────────────────

    def search_emails(self, query: str, max_results: int = 5) -> str:
        """Busca emails com query Gmail (ex: 'from:joao subject:reunião')."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            results = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return f"Nenhum email encontrado para: '{query}'"
            lines = [f"🔍 {len(messages)} resultados para '{query}':"]
            for msg in messages:
                meta = service.users().messages().get(
                    userId="me", id=msg["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ).execute()
                headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
                sender = headers.get("From", "?")
                m = re.search(r'([^<]+)', sender)
                if m:
                    sender = m.group(1).strip()
                lines.append(f"  • {sender}: {headers.get('Subject', 'Sem Assunto')} (ID: {msg['id'][:8]})")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro na busca de emails: {e}"

    # ── Ler email completo ────────────────────────────────────────

    def read_email(self, message_id: str) -> str:
        """Lê o conteúdo completo de um email pelo ID."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            body_text = self._extract_body(msg.get("payload", {}))
            lines = [
                f"📧 Email de {headers.get('From', '?')}",
                f"📌 Assunto: {headers.get('Subject', 'Sem Assunto')}",
                f"📅 Data: {headers.get('Date', '?')}",
                f"---",
                body_text[:3000] if body_text else "(sem conteúdo de texto)"
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao ler email: {e}"

    def _extract_body(self, payload: dict) -> str:
        """Extrai texto do corpo do email (text/plain ou text/html)."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            result = self._extract_body(part)
            if result:
                return result
        if payload.get("body", {}).get("data"):
            raw = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            # Strip HTML tags for readability
            return re.sub(r'<[^>]+>', '', raw)
        return ""

    # ── Enviar email ──────────────────────────────────────────────

    def send_email(self, to: str, subject: str, body: str, attachments: str = "") -> str:
        """Envia email. attachments = caminhos separados por vírgula (ou nomes de arquivo no workspace)."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            file_paths = self._resolve_attachments(attachments) if attachments else []

            if file_paths:
                message = MIMEMultipart()
                message["to"] = to
                message["subject"] = subject
                message.attach(MIMEText(body, "plain"))
                for fp in file_paths:
                    self._attach_file(message, fp)
            else:
                message = MIMEText(body)
                message["to"] = to
                message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            print(f"[Google] Enviando email para {to}: {subject} ({len(file_paths)} anexo(s))")
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            att_msg = f" com {len(file_paths)} anexo(s)" if file_paths else ""
            return f"✅ Email enviado{att_msg} para {to}!\n📧 Assunto: {subject}\n🆔 ID: {sent.get('id', 'N/A')}"
        except Exception as e:
            return f"Erro ao enviar email: {e}"

    # ── Responder email ───────────────────────────────────────────

    def reply_email(self, message_id: str, body: str) -> str:
        """Responde a um email existente pelo ID."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            original = service.users().messages().get(userId="me", id=message_id, format="metadata",
                metadataHeaders=["Subject", "From", "Message-ID"]).execute()
            headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
            to = headers.get("From", "")
            subject = headers.get("Subject", "")
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"
            thread_id = original.get("threadId")
            msg_id = headers.get("Message-ID", "")

            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            if msg_id:
                message["In-Reply-To"] = msg_id
                message["References"] = msg_id

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            sent_body = {"raw": raw}
            if thread_id:
                sent_body["threadId"] = thread_id
            sent = service.users().messages().send(userId="me", body=sent_body).execute()
            return f"✅ Resposta enviada para {to}!\n📧 Assunto: {subject}"
        except Exception as e:
            return f"Erro ao responder email: {e}"

    # ── Encaminhar email ──────────────────────────────────────────

    def forward_email(self, message_id: str, to: str, extra_text: str = "") -> str:
        """Encaminha um email para outro destinatário."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            original = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "")
            if not subject.lower().startswith("fwd:") and not subject.lower().startswith("enc:"):
                subject = f"Fwd: {subject}"
            original_body = self._extract_body(original.get("payload", {}))
            body = f"{extra_text}\n\n---------- Mensagem encaminhada ----------\nDe: {headers.get('From', '?')}\nData: {headers.get('Date', '?')}\nAssunto: {headers.get('Subject', '?')}\n\n{original_body[:5000]}"

            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return f"✅ Email encaminhado para {to}!\n📧 Assunto: {subject}"
        except Exception as e:
            return f"Erro ao encaminhar email: {e}"

    # ── Marcar como lido ──────────────────────────────────────────

    def mark_as_read(self, message_id: str) -> str:
        """Marca um email como lido."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return f"✅ Email marcado como lido (ID: {message_id[:8]}…)"
        except Exception as e:
            return f"Erro ao marcar email: {e}"

    # ── Deletar email ─────────────────────────────────────────────

    def delete_email(self, message_id: str) -> str:
        """Move um email para a lixeira."""
        if not self.available:
            return "Gmail não configurado."
        try:
            service = self._gmail()
            service.users().messages().trash(userId="me", id=message_id).execute()
            return f"✅ Email movido para a lixeira (ID: {message_id[:8]}…)"
        except Exception as e:
            return f"Erro ao deletar email: {e}"

    # ══════════════════════════════════════════════════════════════
    #                     ANEXOS / ARQUIVOS
    # ══════════════════════════════════════════════════════════════

    def _resolve_attachments(self, attachments_str: str) -> List[Path]:
        """Resolve nomes de arquivo: caminho absoluto ou arquivo no workspace."""
        paths = []
        for name in attachments_str.split(","):
            name = name.strip()
            if not name:
                continue
            p = Path(name)
            if p.is_absolute() and p.exists():
                paths.append(p)
            else:
                # Busca no workspace Luna-programming
                wp = WORKSPACE_DIR / name
                if wp.exists():
                    paths.append(wp)
                else:
                    # Tenta busca recursiva
                    found = list(WORKSPACE_DIR.rglob(name))
                    if found:
                        paths.append(found[0])
                    else:
                        print(f"[Google] ⚠ Anexo não encontrado: {name}")
        return paths

    def _attach_file(self, message: MIMEMultipart, filepath: Path):
        """Anexa um arquivo ao email MIME."""
        content_type, _ = mimetypes.guess_type(str(filepath))
        if content_type is None:
            content_type = "application/octet-stream"
        main_type, sub_type = content_type.split("/", 1)
        with open(filepath, "rb") as f:
            attachment = MIMEBase(main_type, sub_type)
            attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", "attachment", filename=filepath.name)
        message.attach(attachment)
        print(f"[Google] 📎 Anexo: {filepath.name} ({content_type})")

    def list_workspace_files(self, pattern: str = "*") -> str:
        """Lista arquivos no workspace Luna-programming."""
        if not WORKSPACE_DIR.exists():
            return "Pasta Luna-programming não encontrada."
        files = sorted(WORKSPACE_DIR.glob(pattern))
        if not files:
            return f"Nenhum arquivo encontrado com o padrão '{pattern}'."
        lines = [f"📁 Arquivos em Luna-programming ({len(files)}):"]
        for f in files[:30]:
            size = f.stat().st_size
            if size < 1024:
                sz = f"{size}B"
            elif size < 1024 * 1024:
                sz = f"{size // 1024}KB"
            else:
                sz = f"{size // (1024*1024)}MB"
            lines.append(f"  • {f.name} ({sz})")
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════════
    #                       GOOGLE DRIVE
    # ══════════════════════════════════════════════════════════════

    def google_drive_upload(self, filepath_or_name: str, folder_id: str = None) -> str:
        """Envia um arquivo para o Google Drive e retorna um link público/compartilhável."""
        if not self.available:
            return "Google Drive não configurado."
        try:
            service = self._drive()
            # Resolve caminhos na pasta Luna-programming ou absoluto
            paths = self._resolve_attachments(filepath_or_name)
            if not paths:
                return f"⚠ Arquivo '{filepath_or_name}' não encontrado no workspace ou sistema."
            
            filepath = paths[0]
            filename = filepath.name
            
            content_type, _ = mimetypes.guess_type(str(filepath))
            if content_type is None:
                content_type = "application/octet-stream"

            file_metadata = {'name': filename}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            print(f"[Google Drive] Subindo arquivo {filename} ({content_type})...")
            media = MediaFileUpload(str(filepath), mimetype=content_type, resumable=True)
            file = service.files().create(
                body=file_metadata, media_body=media, 
                fields='id, name, webViewLink'
            ).execute()
            
            file_id = file.get("id")
            web_link = file.get("webViewLink", "N/A")

            # Torna o link legível/público (compartilha como leitor com qualquer um)
            try:
                service.permissions().create(
                    fileId=file_id,
                    body={'type': 'anyone', 'role': 'reader'}
                ).execute()
                share_status = "🔓 Link público ativado!"
            except Exception as e:
                share_status = f"⚠ Não foi possível ativar link público: {e}"

            return f"✅ Arquivo '{filename}' enviado com sucesso para o Google Drive!\n🆔 ID: {file_id}\n🔗 Link: {web_link}\n{share_status}"
        except Exception as e:
            return f"Erro ao enviar arquivo para o Google Drive: {e}"

    def google_drive_list(self, max_results: int = 10) -> str:
        """Lista os últimos arquivos enviados ao Google Drive."""
        if not self.available:
            return "Google Drive não configurado."
        try:
            service = self._drive()
            results = service.files().list(
                pageSize=max_results, 
                fields="nextPageToken, files(id, name, mimeType, webViewLink)"
            ).execute()
            items = results.get('files', [])
            if not items:
                return "Nenhum arquivo encontrado no seu Google Drive."
            
            lines = ["🗂 Seus arquivos recentes no Google Drive:"]
            for item in items:
                icon = "📁" if item['mimeType'] == 'application/vnd.google-apps.folder' else "📄"
                lines.append(f"  • {icon} {item['name']} (ID: {item['id'][:8]}...) - {item.get('webViewLink', 'Sem link')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao listar arquivos do Google Drive: {e}"

    def google_drive_search(self, query: str, max_results: int = 10) -> str:
        """Pesquisa arquivos no Drive (busca parcial por nome)."""
        if not self.available:
            return "Google Drive não configurado."
        try:
            service = self._drive()
            # Escapa aspas simples na query
            safe_query = query.replace("'", "\\'")
            q_str = f"name contains '{safe_query}' and trashed = false"
            
            results = service.files().list(
                q=q_str, pageSize=max_results,
                fields="files(id, name, mimeType, webViewLink)"
            ).execute()
            items = results.get('files', [])
            if not items:
                return f"Nenhum arquivo encontrado para a busca '{query}'."
            
            lines = [f"🔍 Resultados no Drive para '{query}':"]
            for item in items:
                icon = "📁" if item['mimeType'] == 'application/vnd.google-apps.folder' else "📄"
                lines.append(f"  • {icon} {item['name']} (ID: {item['id'][:8]}...) - {item.get('webViewLink', 'Sem link')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao buscar no Google Drive: {e}"

    def google_drive_create_folder(self, folder_name: str, parent_id: str = None) -> str:
        """Cria uma nova pasta no Google Drive."""
        if not self.available:
            return "Google Drive não configurado."
        try:
            service = self._drive()
            metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                metadata['parents'] = [parent_id]
                
            folder = service.files().create(body=metadata, fields='id, name, webViewLink').execute()
            return f"✅ Pasta '{folder_name}' criada com sucesso no Google Drive!\n🆔 ID: {folder.get('id')}\n🔗 Link: {folder.get('webViewLink')}"
        except Exception as e:
            return f"Erro ao criar pasta no Google Drive: {e}"

    def google_drive_delete(self, file_id: str) -> str:
        """Envia um arquivo ou pasta para a lixeira do Google Drive."""
        if not self.available:
            return "Google Drive não configurado."
        try:
            service = self._drive()
            service.files().update(fileId=file_id, body={'trashed': True}).execute()
            return f"✅ Arquivo/Pasta movido para a lixeira com sucesso! (ID: {file_id[:8]}...)"
        except Exception as e:
            return f"Erro ao deletar arquivo no Google Drive: {e}"

    # ── Handler de texto natural ──────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()
        # Calendar - leitura
        if any(w in tl for w in ["compromisso", "compromissos", "calendário", "calendario", "agenda", "reunião", "reuniao"]):
            return self.get_calendar_events()
        # Gmail - leitura
        if any(w in tl for w in ["email", "emails", "e-mail", "e-mails"]):
            if any(w in tl for w in ["enviar", "envie", "manda", "mande", "escreva", "escrever"]):
                return None  # Deixa o LLM decidir os parâmetros
            return self.get_unread_emails()
        return None


# Singleton
_google_instance: Optional[GoogleManager] = None

def get_google() -> GoogleManager:
    global _google_instance
    if _google_instance is None:
        _google_instance = GoogleManager()
    return _google_instance
