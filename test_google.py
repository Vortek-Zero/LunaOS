#!/usr/bin/env python3
import os, sys
sys.path.append(os.path.abspath('.'))
from actions.google_services import get_google

def main():
    gm = get_google()
    print('Available:', gm.available)
    if gm.available:
        print("\n--- TESTE 1: PRÓXIMOS COMPROMISSOS ---")
        print(gm.get_calendar_events())
        
        print("\n--- TESTE 2: LISTAR EMAILS ---")
        print(gm.get_unread_emails())
        
        print("\n--- TESTE 3: CRIANDO EVENTO ---")
        now = "2026-05-21T10:00:00-03:00"
        print(gm.create_calendar_event("Reunião de Teste com Luna", now))
        
        print("\n--- TESTE 4: ENVIANDO EMAIL ---")
        print(gm.send_email("miguelpera282@gmail.com", "Assunto Teste Luna", "Olá, email enviado pela Luna!"))

        print("\n--- TESTE 5: GOOGLE DRIVE LIST ---")
        print(gm.google_drive_list(5))
    else:
        print('Google não configurado/disponível')

if __name__ == '__main__':
    main()
