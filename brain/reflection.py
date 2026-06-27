"""
brain/reflection.py — Sistema de Reflexão e Verificação (inspirado no Agent-S)
Após executar ações, verifica se o resultado é real e detecta alucinações.
"""
import re
from pathlib import Path
from typing import Optional
from config import WORKSPACE_DIR

class OutputValidator:
    """
    Validador de saída do LLM. Inspirado no format checker do Agent-S.
    Verifica se a resposta do LLM é factualmente consistente com as ações executadas.
    """

    @staticmethod
    def check_hallucination(response: str, observations: list[str],
                            user_text: str = "") -> Optional[str]:
        """
        Verifica se a resposta do LLM contém alegações não suportadas pelas observações.
        Retorna feedback de correção se detectar problema, None se ok.
        """
        resp_lower = response.lower()
        obs_text = " ".join(o.lower() for o in observations)

        # Detecta alegações de criação sem evidência nas observações
        creation_claims = [
            "criei", "criado", "criei o arquivo", "arquivo criado",
            "projeto criado", "pasta criada", "foi criado",
            "salvei o arquivo", "arquivo salvo", "escrevi", "enviei", "mandei"
        ]
        
        # Se alegou criação/ação
        has_claimed_creation = any(claim in resp_lower for claim in creation_claims)
        
        # Se temos evidência de sucesso nas observações
        has_evidence = (
            "sucesso" in obs_text
            and any(kw in obs_text for kw in ["arquivo", "código", "criado", "projeto", "bytes", "enviado", "salvo"])
        )

        if has_claimed_creation and not has_evidence and observations:
            return (
                "⚠️ ALERTA: Você disse que executou uma ação, mas as observações reais não confirmam o sucesso. "
                "NÃO minta para o usuário. Informe que houve um problema ou que a ação não foi concluída."
            )

        # Detecta menção a "lista de compras" quando irrelevante
        user_lower = user_text.lower() if user_text else ""
        user_talk_about_shopping = any(w in user_lower for w in ["compras", "comprar", "shopping"])
        shopping_in_obs = any("compras" in o.lower() for o in observations)
        shopping_in_resp = "lista de compras" in resp_lower or "compras" in resp_lower

        if shopping_in_resp and not user_talk_about_shopping and not shopping_in_obs:
            return (
                "⚠️ ALERTA: Você mencionou a lista de compras sem necessidade. "
                "Só mencione estado do sistema quando for relevante ao assunto."
            )

        return None

    @staticmethod
    def check_tool_honesty(tool_name: str, result: str) -> bool:
        """
        Verifica se o resultado de uma ferramenta é honesto.
        Retorna True se for honesto, False se parecer alucinação.
        """
        if not result or result.strip() == "":
            return False

        result_upper = result.upper()

        # Se falhou explicitamente, é honesto (admite erro)
        if result_upper.startswith("FALHOU"):
            return True

        # Ferramentas que escrevem arquivos DEVEM ter evidência concreta de sucesso
        write_tools = ["write_code", "create_project", "filesystem", "document_services"]
        if any(t in tool_name for t in write_tools):
            if result_upper.startswith("SUCESSO"):
                has_evidence = any(
                    indicator in result.lower()
                    for indicator in ["arquivo salvo", "código escrito", "bytes", "criado com sucesso"]
                )
                if not has_evidence:
                    return False  # alegou sucesso mas sem evidência
            else:
                return False  # resultado ambíguo para ferramenta de escrita

        return True


class VerificationSystem:
    """
    Sistema de verificação pós-execução inspirado no Reflection Agent do Agent-S.
    Após uma ferramenta de escrita ser executada, verifica se o arquivo existe no disco.
    """

    WORKSPACE = WORKSPACE_DIR

    @classmethod
    def verify_file_creation(cls, filepath: str) -> dict:
        """Verifica se um arquivo foi realmente criado."""
        fp = Path(filepath)
        if not fp.exists():
            return {"success": False, "reason": "Arquivo não encontrado no disco."}
        size = fp.stat().st_size
        if size == 0:
            return {"success": False, "reason": "Arquivo vazio (0 bytes)."}
        return {"success": True, "size": size, "path": str(fp)}

    @classmethod
    def verify_in_workspace(cls, filename: str) -> dict:
        """Verifica se o arquivo está no workspace."""
        fp = cls.WORKSPACE / filename
        return cls.verify_file_creation(str(fp))

    @classmethod
    def verify_directory_created(cls, dirpath: str) -> dict:
        """Verifica se um diretório foi criado."""
        dp = Path(dirpath)
        if not dp.exists():
            return {"success": False, "reason": "Diretório não encontrado."}
        if not dp.is_dir():
            return {"success": False, "reason": "Caminho existe mas não é um diretório."}
        contents = list(dp.iterdir())
        return {
            "success": True,
            "path": str(dp),
            "files_count": len(contents),
            "files": [c.name for c in contents[:20]],
        }
