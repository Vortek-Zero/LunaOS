#!/usr/bin/env python3
"""
brain/safety.py — Módulo de segurança cognitiva e filtros anti-abuso.
Filtra inputs perigosos antes de passarem pelo LLM ou pelas ferramentas do sistema.
"""
import re
import unicodedata
from typing import Optional

# Respostas padrão
REFUSAL_RESPONSE = "Desculpa, mas eu não posso ajudar com isso. Esse tipo de coisa vai contra meus princípios de segurança."
SELF_HARM_RESPONSE = "Eu me preocupo com você. Se estiver passando por um momento difícil, por favor procure ajuda profissional. O CVV (Centro de Valorização da Vida) atende 24h pelo telefone 188 ou pelo chat online em cvv.org.br."

# Padrões regex para cada categoria de risco
SAFETY_PATTERNS = [
    {
        "category": "self_harm",
        "patterns": [
            r"me matar",
            r"suicid",
            r"quero morrer",
            r"tirar minha vida",
            r"me enforcar",
            r"cortar meus? pulsos?",
            r"automutila",
            r"como me suicidar",
            r"beber veneno para morrer",
            r"dar um fim na minha vida",
            r"acabar com a minha vida"
        ],
        "response": SELF_HARM_RESPONSE
    },
    {
        "category": "violence_and_weapons",
        "patterns": [
            r"(fazer|criar|construir|fabricar|receita de|como montar).*bomba",
            r"bomba caseira",
            r"coquetel molotov",
            r"explosivos? caseiros?",
            r"como fazer pólvora",
            r"(como|receita para) envenenar",
            r"como matar (alguem|uma pessoa|pessoas)",
            r"como assassinar",
            r"como esfaquear",
            r"como atirar em (alguem|pessoas)",
            r"(fabricar|fazer|construir) (uma )?arma de fogo",
            r"veneno caseiro para (pessoas|humanos|alguem)"
        ],
        "response": REFUSAL_RESPONSE
    },
    {
        "category": "drugs",
        "patterns": [
            r"(sintetizar|fazer|produzir|fabricar|receita de) (drogas?|metanfetamina|cocaina|crack|lsd|heroina|lança perfume)",
            r"(traficar|comprar|vender) (drogas?|cocaina|crack|lsd|heroina|metanfetamina)"
        ],
        "response": REFUSAL_RESPONSE
    },
    {
        "category": "hacking",
        "patterns": [
            r"(hackear|invadir|derrubar|pichar).*(site|servidor|computador|sistema|rede|banco|wifi|vizinho|nasa|governo|contas?)",
            r"(criar|escrever|fazer).*(ransomware|malware|virus de computador|spyware|trojan)",
            r"(roubar|clonar|gerar).*(cartoes?|senhas?|dados bancarios)"
        ],
        "response": REFUSAL_RESPONSE
    }
]

def normalize_text(text: str) -> str:
    """Normaliza o texto (remove acentos, pontuações e põe em minúsculas)."""
    if not text:
        return ""
    # Remove acentuação
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Põe em minúsculas
    text = text.lower()
    # Mantém letras, números e espaços, remove pontuação
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()

def check_safety(user_input: str) -> Optional[str]:
    """
    Verifica se o input do usuário contém algum tópico banido ou padrão de auto-lesão.
    Retorna a mensagem de recusa adequada se for inseguro, ou None se for seguro.
    """
    normalized = normalize_text(user_input)
    if not normalized:
        return None

    # Verifica os padrões regex
    for group in SAFETY_PATTERNS:
        for pattern in group["patterns"]:
            # Normaliza o padrão regex (remove acentos) para bater com o texto normalizado
            norm_pattern = unicodedata.normalize("NFD", pattern)
            norm_pattern = "".join(c for c in norm_pattern if unicodedata.category(c) != "Mn")
            
            # Executa a busca regex
            if re.search(norm_pattern, normalized, re.IGNORECASE):
                return group["response"]

    return None

if __name__ == "__main__":
    # Testes unitários rápidos
    test_cases = [
        ("Como eu faço para me matar?", "Eu me preocupo com você"),
        ("Como construir uma bomba caseira no quintal?", "contra meus princípios"),
        ("Luna, crie uma planilha de receitas de bolo.", None),
        ("quero hackear o site da NASA", "contra meus princípios"),
        ("como fazer um veneno caseiro para ratos?", None),  # Ratos deve ser seguro!
        ("como fazer um veneno caseiro para pessoas?", "contra meus princípios")  # Pessoas deve ser bloqueado!
    ]
    
    print("Executando testes rápidos de segurança...")
    all_passed = True
    for text, expected in test_cases:
        res = check_safety(text)
        if expected is None:
            passed = res is None
        else:
            passed = res is not None and expected in res
        print(f"Input: '{text}'\n  -> Resposta: '{res}'\n  -> Passou: {passed}")
        if not passed:
            all_passed = False
            
    print(f"\nResultado dos testes: {'✓ Passou em tudo!' if all_passed else '✗ Falhou em algo.'}")
