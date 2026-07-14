#!/usr/bin/env python3
"""
tests/cognitive_tests.py — Suite de testes cognitivos para a Luna v1.4.1.
Simula prompts de usuários e verifica se o sistema de memória, reflexão e planner respondem adequadamente em test_mode.
"""
import unittest
import sys
from pathlib import Path

# Adiciona a raiz do projeto para importar módulos
sys.path.append(str(Path(__file__).parent.parent))

from luna_core import get_luna, _luna_instance

class TestLunaCognitiveArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reinicia o singleton para forçar test_mode=True
        import luna_core
        luna_core._luna_instance = None
        cls.luna = get_luna(test_mode=True)
        print("[CognitiveTests] Iniciado LunaCore em test_mode.")

    def test_01_reminder_creation(self):
        """Teste se a Luna aciona a ferramenta correta para criar um lembrete e entende o contexto de tempo."""
        prompt = "Me lembra amanhã às 10h de estudar programação em Rust."
        
        # Chamada assíncrona/process_query (estamos usando a versão sincronizada para teste)
        # process_query retorna o texto que a Luna falaria
        response = self.luna.process(prompt)
        
        self.assertIsNotNone(response, "A resposta não deveria ser nula.")
        
        # A resposta deve conter indicação de sucesso (já que em test_mode o tool call retorna [TEST MODE] SUCESSO)
        response_lower = response.lower()
        
        # Verifica menção às entidades chave
        self.assertTrue(
            "rust" in response_lower or "lembrete" in response_lower or "programação" in response_lower,
            f"Resposta não capturou a intenção do lembrete. Recebido: {response}"
        )

    def test_02_context_continuation(self):
        """Teste de memória episódica: pedir continuidade sem especificar o tópico completo."""
        prompt = "Continue o que estávamos falando ontem sobre Python."
        response = self.luna.process(prompt)
        
        self.assertIsNotNone(response)
        self.assertGreater(len(response), 10, "A resposta está muito curta para um pedido de continuidade.")
        # O fato de não crachar e dar uma resposta já é um passe inicial para o fluxo de memória
        
    def test_03_profile_update(self):
        """Teste se a Luna entende a mudança de preferência e aciona a memória (embora o mock evite write real, ela deve planejar isso)."""
        prompt = "Passei a usar Firefox no lugar do Chrome. Não uso mais o Chrome para trabalhar."
        response = self.luna.process(prompt)
        
        response_lower = response.lower()
        self.assertTrue(
            "firefox" in response_lower or "atualiz" in response_lower or "anotad" in response_lower or "lembrar" in response_lower,
            f"Resposta não refletiu a atualização de perfil. Recebido: {response}"
        )

if __name__ == "__main__":
    unittest.main()
