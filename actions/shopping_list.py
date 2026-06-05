#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path
from config import DATA_DIR
from voice.tts import get_tts

SHOPPING_LIST_FILE = DATA_DIR / "shopping_list.json"

class ShoppingListManager:
    def __init__(self):
        self.file = SHOPPING_LIST_FILE

    def _load(self):
        if not self.file.exists():
            return {"items": []}
        try:
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"items": []}

    def _save(self, data):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def format_list(self) -> str:
        data = self._load()
        items = data.get("items", [])
        if not items:
            return "Sua lista de compras está vazia."
        return "Sua lista de compras:\n" + "\n".join(f"- {item}" for item in items)

    def handle(self, command: str) -> str:
        command = command.lower()
        data = self._load()
        items = data.get("items", [])
        tts = get_tts()

        if "adiciona" in command or "adicionar" in command or "adicione" in command or "coloca" in command:
            # Extrai o item via regex para ser mais robusto
            m = re.search(
                r'(?:adiciona|adicione|adicionar|coloca)\s+(.+?)(?:\s+(?:na|à)\s+lista.*)?$',
                command
            )
            if m:
                item = m.group(1).strip()
                if item:
                    if any(i.lower() == item.lower() for i in items):
                        return f"O item '{item}' já está na sua lista."
                    items.append(item)
                    data["items"] = items
                    self._save(data)
                    return f"Adicionei {item} à sua lista de compras."

        if "remove" in command or "remover" in command or "comprei" in command or "tira" in command:
            for i, item in enumerate(items):
                if item.lower() in command:
                    removed = items.pop(i)
                    data["items"] = items
                    self._save(data)
                    return f"Pronto, marquei {removed} como comprado."
            return "Não encontrei esse item na lista para remover."

        if "limpa" in command or "limpar" in command or "apaga" in command:
            data["items"] = []
            self._save(data)
            return "A lista de compras foi limpa."

        if "leia" in command or "ler" in command or "ver" in command or "quais" in command or "lista" in command:
            if not items:
                return "A sua lista de compras está vazia."
            
            items_str = ", ".join(items)
            if "leia" in command or "ler" in command or "fala" in command:
                tts.speak(f"Na sua lista de compras tem: {items_str}", blocking=False)
            return self.format_list()

        return ""

_instance = None
def get_shopping_list() -> ShoppingListManager:
    global _instance
    if _instance is None:
        _instance = ShoppingListManager()
    return _instance
