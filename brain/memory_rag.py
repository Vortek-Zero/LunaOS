#!/usr/bin/env python3
"""
brain/memory_rag.py — Memória de longo prazo via ChromaDB
Coleções: luna_memory (fatos do usuário) + write_universe (fatos ficcionais)
"""
import os
import chromadb
from pathlib import Path
import urllib.request
import json
import time

BASE_DIR = Path(__file__).parent.parent
DB_DIR = BASE_DIR / "brain" / "chroma_db"

class MemoryRAG:
    """Sistema de Memória de Longo Prazo via RAG e embeddings locais."""

    def __init__(self):
        try:
            self.client = chromadb.PersistentClient(path=str(DB_DIR))
            self.collection = self.client.get_or_create_collection(name="luna_memory")
            self.write_collection = self.client.get_or_create_collection(name="write_universe")
            self.home_collection = self.client.get_or_create_collection(name="home_info")
            self.enabled = True
            print(f"[MemoryRAG] ✓ Banco Vetorial ChromaDB iniciado (Memórias: {self.collection.count()}, Casa: {self.home_collection.count()}).")
        except Exception as e:
            print(f"[MemoryRAG] ⚠ Erro ao iniciar ChromaDB: {e}")
            self.enabled = False

    def _get_embedding(self, text: str) -> list[float]:
        """Obtém embedding via Ollama. Retorna [] se indisponível."""
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/embeddings",
                data=json.dumps({
                    "model": "nomic-embed-text",
                    "prompt": text
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("embedding", [])
        except Exception:
            return []  # Fallback silencioso — usa busca por keywords

    def _keyword_search(self, collection, query: str, n_results: int = 3) -> list[str]:
        """Busca por keywords quando embeddings não estão disponíveis."""
        try:
            total = collection.count()
            if total == 0:
                return []
            # Pega todos os documentos e filtra por palavras-chave
            all_docs = collection.get(limit=min(total, 200))
            documents = all_docs.get("documents", [])
            query_words = set(w.lower() for w in query.split() if len(w) > 3)
            scored = []
            for doc in documents:
                if not doc:
                    continue
                doc_lower = doc.lower()
                score = sum(1 for w in query_words if w in doc_lower)
                if score > 0:
                    scored.append((score, doc))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [doc for _, doc in scored[:n_results]]
        except Exception:
            return []

    def remember(self, text: str, source: str = "user"):
        """Salva uma memória do usuário no banco vetorial."""
        if not self.enabled or not text.strip():
            return
        import uuid
        emb = self._get_embedding(text)
        timestamp = time.time()
        doc_id = str(uuid.uuid4())
        try:
            if emb:
                self.collection.add(
                    documents=[text],
                    embeddings=[emb],
                    metadatas=[{"source": source, "timestamp": timestamp}],
                    ids=[doc_id]
                )
            else:
                # Salva sem embedding (ChromaDB usa busca por keywords)
                self.collection.add(
                    documents=[text],
                    metadatas=[{"source": source, "timestamp": timestamp}],
                    ids=[doc_id]
                )
        except Exception as e:
            print(f"[MemoryRAG] Erro ao salvar memória: {e}")

    def remember_story_fact(self, project_id: str, fact: str, category: str = "historia"):
        """Persiste fatos do universo ficcional separados por projeto."""
        if not self.enabled or not fact.strip():
            return
        import uuid
        emb = self._get_embedding(fact)
        doc_id = str(uuid.uuid4())
        try:
            meta = {"project_id": project_id, "category": category, "timestamp": time.time()}
            if emb:
                self.write_collection.add(
                    documents=[fact], embeddings=[emb], metadatas=[meta], ids=[doc_id]
                )
            else:
                self.write_collection.add(
                    documents=[fact], metadatas=[meta], ids=[doc_id]
                )
        except Exception as e:
            print(f"[MemoryRAG] Erro ao salvar fato de história: {e}")

    def retrieve_context(self, query: str, n_results: int = 3) -> str:
        """Busca memórias relevantes do usuário."""
        if not self.enabled or self.collection.count() == 0:
            return ""
        emb = self._get_embedding(query)
        try:
            if emb:
                results = self.collection.query(
                    query_embeddings=[emb],
                    n_results=min(n_results, self.collection.count())
                )
                docs = results.get("documents", [[]])[0]
            else:
                docs = self._keyword_search(self.collection, query, n_results)
            if docs:
                return "[MEMÓRIAS PROFUNDAS RELEVANTES (RAG)]\n" + "\n".join(f"- {d}" for d in docs)
        except Exception:
            pass
        return ""

    def recall_story_context(self, project_id: str, query: str, n_results: int = 5) -> str:
        """Busca fatos do universo ficcional de um projeto específico."""
        if not self.enabled or self.write_collection.count() == 0:
            return ""
        emb = self._get_embedding(query)
        try:
            where = {"project_id": project_id}
            if emb:
                results = self.write_collection.query(
                    query_embeddings=[emb],
                    n_results=min(n_results, self.write_collection.count()),
                    where=where
                )
                docs = results.get("documents", [[]])[0]
            else:
                all_docs = self.write_collection.get(where=where)
                docs = all_docs.get("documents", [])[:n_results]
            if docs:
                return "[UNIVERSO FICCIONAL — fatos estabelecidos]\n" + "\n".join(f"- {d}" for d in docs)
        except Exception:
            pass
        return ""

    def remember_home_info(self, text: str, category: str = "geral") -> str:
        """Salva uma informação sobre a casa (wifi, chaves, tarefas, etc.) no banco vetorial."""
        if not self.enabled or not text.strip():
            return "FALHOU: RAG desabilitado ou texto vazio."
        import uuid
        emb = self._get_embedding(text)
        doc_id = str(uuid.uuid4())
        try:
            meta = {"category": category, "timestamp": time.time()}
            if emb:
                self.home_collection.add(
                    documents=[text], embeddings=[emb], metadatas=[meta], ids=[doc_id]
                )
            else:
                self.home_collection.add(
                    documents=[text], metadatas=[meta], ids=[doc_id]
                )
            return f"✓ Informação sobre a casa registrada: '{text}'"
        except Exception as e:
            return f"FALHOU: Erro ao salvar informação da casa: {e}"

    def retrieve_home_info(self, query: str, n_results: int = 3) -> str:
        """Busca informações salvas sobre a casa."""
        if not self.enabled or self.home_collection.count() == 0:
            return ""
        emb = self._get_embedding(query)
        try:
            if emb:
                results = self.home_collection.query(
                    query_embeddings=[emb],
                    n_results=min(n_results, self.home_collection.count())
                )
                docs = results.get("documents", [[]])[0]
            else:
                docs = self._keyword_search(self.home_collection, query, n_results)
            if docs:
                return "[INFORMAÇÕES SOBRE A CASA (RAG)]\n" + "\n".join(f"- {d}" for d in docs)
        except Exception:
            pass
        return ""

