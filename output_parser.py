#!/usr/bin/env python3
"""
Output Parser e Self-Correction para Qwen 2.5:3b
Valida respostas e detecta alucinações/incertezas
"""

import re
import json
from typing import Dict, Tuple, Optional
from enum import Enum

class ConfidenceLevel(Enum):
    HIGH = "high"           # Resposta confiante e factual
    MEDIUM = "medium"       # Resposta parcialmente confiante
    LOW = "low"             # Resposta incerta ou vaga
    UNCERTAIN = "uncertain" # Resposta com sinais de incerteza
    HALLUCINATION = "hallucination"  # Possível alucinação detectada

class OutputParser:
    """Parser inteligente com detecção de alucinações e self-correction"""
    
    # Sinais de incerteza padrão que indicam falta de conhecimento real
    UNCERTAINTY_PHRASES = [
        "não tenho certeza",
        "não sou totalmente certo",
        "pode ser que",
        "talvez",
        "é possível que",
        "supostamente",
        "alegadamente",
        "segundo alguns",
        "aparentemente",
        "parece que",
        "eu acho que",
        "em minha opinião",
        "acho que",
        "imagino que",
        "presumo que",
        "acredito que",
        "não tenho dados",
        "sem saber",
        "não posso afirmar",
        "desculpe, não sei",
        "não encontrei",
        "não consegui encontrar",
        "não há informações",
        "dentre as minhas limitações",
        "fora do meu conhecimento",
    ]
    
    # Sinais de possível alucinação — só disparam quando o LLM fala sobre SI MESMO
    HALLUCINATION_PATTERNS = [
        r"(?:eu|minha resposta|o que disse).*(?:confabulei|inventei|é ficção|é imaginário)",
        r".*(?:não existe|não é real|é totalmente falso).*",
        r".*(?:foi um erro|estava errado|me enganei).*",
        r"como um \d{4} específico\b",
        r"segundo.*?(?:que não consigo verificar|fictício)",
        r"não (tenho acesso a|posso acessar|consigo ver) (informações|dados) (em tempo real|atuais|recentes)",
        r"de acordo com minha (base de dados|memória|treinamento)",
        r"até a (data|ano) do meu treinamento",
        r"corte de conhecimento",
        r"não foi possível (verificar|confirmar|validar)",
        r"essa (informação|resposta) pode (estar desatualizada|não ser precisa)",
        r"recomendo (verificar|confirmar|pesquisar)",
        r"não (posso|consigo) (responder|afirmar|confirmar) com (certeza|precisão)",
        r"\b(\d{4})\b.*\b(\d{4})\b",  # multiple years cited (often hallucinated)
    ]
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
    
    def _log(self, msg: str):
        """Log interno para debug"""
        if self.verbose:
            print(f"[PARSER] {msg}")
    
    def detect_confidence(self, text: str) -> ConfidenceLevel:
        """Detecta nível de confiança baseado em padrões de linguagem"""
        text_lower = text.lower()
        
        # Verifica sinais de incerteza
        uncertainty_count = sum(1 for phrase in self.UNCERTAINTY_PHRASES if phrase in text_lower)
        uncertainty_ratio = uncertainty_count / max(1, len(text_lower.split()))
        
        self._log(f"Uncertainty count: {uncertainty_count}, ratio: {uncertainty_ratio:.2f}")
        
        # Verifica hallucinations
        for pattern in self.HALLUCINATION_PATTERNS:
            if re.search(pattern, text_lower):
                self._log(f"Possível hallucination: {pattern}")
                return ConfidenceLevel.HALLUCINATION
        
        # Classifica por ratio de incerteza
        if uncertainty_count >= 3 or uncertainty_ratio > 0.2:
            return ConfidenceLevel.UNCERTAIN
        
        if uncertainty_count >= 1 or uncertainty_ratio > 0.1:
            return ConfidenceLevel.MEDIUM
        
        if len(text) < 20:  # Respostas muito curtas são suspeitas
            return ConfidenceLevel.LOW
        
        return ConfidenceLevel.HIGH
    
    def parse_json_response(self, response: str) -> Dict:
        """
        Extrai e valida JSON da resposta
        Tenta múltiplas estratégias de parsing
        """
        self._log(f"Parsing response: {response[:100]}...")
        
        # Estratégia 1: JSON entre chaves
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                self._log("Successfully parsed JSON")
                return parsed
            except json.JSONDecodeError:
                self._log("Failed to parse found JSON")
        
        # Estratégia 2: Se não houver JSON, cria um estruturado
        self._log("No valid JSON found, creating default structure")
        return self._create_default_response(response)
    
    def _create_default_response(self, text: str) -> Dict:
        """Cria resposta estruturada padrão do texto"""
        return {
            "acoes": [{"action": "conversar"}],
            "resposta": text.strip(),
            "confidence": self.detect_confidence(text).value
        }
    
    def validate_response(self, response_dict: Dict) -> Tuple[bool, Optional[str]]:
        """
        Valida estrutura e conteúdo da resposta
        
        Returns:
            (is_valid, error_message)
        """
        # Verifica campos obrigatórios
        if not isinstance(response_dict, dict):
            return False, "Response is not a dictionary"
        
        if "acoes" not in response_dict:
            return False, "Missing 'acoes' field"
        
        if "resposta" not in response_dict or not response_dict["resposta"]:
            return False, "Missing or empty 'resposta' field"
        
        # Valida estrutura de ações
        acoes = response_dict["acoes"]
        if not isinstance(acoes, list) or not acoes:
            return False, "Invalid 'acoes' structure (should be non-empty list)"
        
        for acao in acoes:
            if not isinstance(acao, dict) or "action" not in acao:
                return False, f"Invalid action structure: {acao}"
        
        # Verifica resposta muito curta ou vazia
        resposta = response_dict["resposta"]
        if len(resposta.strip()) < 3:
            return False, "Response is too short"
        
        return True, None
    
    def correct_response(self, response_dict: Dict, original_query: str = "") -> Dict:
        corrected = response_dict.copy()
        confidence = self.detect_confidence(response_dict.get("resposta", ""))
        if confidence == ConfidenceLevel.HALLUCINATION:
            corrected["_trigger_research"] = True
        corrected["confidence"] = confidence.value
        
        # If original_query provided, append it for research
        if original_query:
            corrected["_original_query"] = original_query
            
        return corrected
    
    def should_retry_search(self, response_dict: Dict) -> bool:
        """
        Determina se a resposta requer novo search/busca na base
        Usado para self-correction iterativa
        """
        resposta = response_dict.get("resposta", "").lower()
        
        # Verifica sinais que indicam resposta insuficiente
        retry_patterns = [
            "não encontrei",
            "não há informações",
            "não consegui",
            "sem dados",
            "desconheço",
            "fora do meu conhecimento",
            "alucinação detectada",
            response_dict.get("_trigger_research", False)
        ]
        
        return any(
            pattern in resposta if isinstance(pattern, str) else pattern
            for pattern in retry_patterns
        )
    
    def improve_specificity(self, response_dict: Dict, context: str = "") -> Dict:
        """
        Melhora especificidade da resposta usando contexto
        Se contexto disponível, integra dados factuais
        """
        improved = response_dict.copy()
        
        resposta = improved.get("resposta", "")
        
        # Se resposta é genérica mas há contexto, tenta ser mais específico
        if context and len(context) > 50:
            # Verifica se resposta é genérica
            generic_patterns = [
                "eu diria que",
                "em geral",
                "tipicamente",
                "provavelmente"
            ]
            
            if any(p in resposta.lower() for p in generic_patterns):
                # Marca como melhorável, alguém pode usar contexto para enriquecer
                improved["_improved_with_context"] = True
        
        return improved


# Teste básico
if __name__ == "__main__":
    parser = OutputParser(verbose=True)
    
    # Teste 1: Resposta confiante
    test1 = {
        "acoes": [{"action": "conversar"}],
        "resposta": "A capital do Brasil é Brasília, localizada no Distrito Federal."
    }
    
    # Teste 2: Resposta incerta
    test2 = {
        "acoes": [{"action": "conversar"}],
        "resposta": "Acho que talvez a capital seja Brasília, mas não tenho certeza."
    }
    
    # Teste 3: Possível hallucination
    test3 = {
        "acoes": [{"action": "conversar"}],
        "resposta": "O presidente do Brasil em 2025 é João Silva, conforme a ficção."
    }
    
    print("\n=== TESTE 1 ===")
    print(f"Confiança: {parser.detect_confidence(test1['resposta'])}")
    corrected1 = parser.correct_response(test1)
    print(f"Corrigido: {corrected1}")
    
    print("\n=== TESTE 2 ===")
    print(f"Confiança: {parser.detect_confidence(test2['resposta'])}")
    corrected2 = parser.correct_response(test2)
    print(f"Corrigido: {corrected2}")
    
    print("\n=== TESTE 3 ===")
    print(f"Confiança: {parser.detect_confidence(test3['resposta'])}")
    corrected3 = parser.correct_response(test3)
    print(f"Corrigido: {corrected3}")
