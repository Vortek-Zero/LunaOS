#!/usr/bin/env python3
"""
RAG Manager - Retrieval-Augmented Generation simplificado
Chunking eficiente, armazenamento local e recuperação por relevância
Sem dependências pesadas (sem chromadb, sem sentence-transformers)
"""

import json
import re
import os
from typing import List, Dict, Tuple
from datetime import datetime

class RAGManager:
    """Gerenciador de RAG local com chunking inteligente e recuperação por similitude"""
    
    def __init__(self, db_path: str = "/home/pera/Luna/rag_db.json", max_chunk_tokens: int = 512):
        self.db_path = db_path
        self.max_chunk_tokens = max_chunk_tokens  # ~2-4 chars per token em média
        self.max_chunk_chars = max_chunk_tokens * 3  # Aproximação conservadora
        self.data = self._load_db()
    
    def _load_db(self) -> Dict:
        """Carrega banco RAG do JSON"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[RAG WARN] Erro ao carregar DB: {e}")
        return {"documents": [], "chunks": [], "metadata": {}}
    
    def _save_db(self):
        """Persiste banco RAG"""
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RAG WARN] Erro ao salvar DB: {e}")
    
    def _tokenize_estimate(self, text: str) -> int:
        """Estima tokens (aproximado: 1 token ≈ 3 caracteres)"""
        return len(text) // 3 + 1
    
    def _split_into_chunks(self, text: str, doc_id: str) -> List[Dict]:
        """
        Divide texto em chunks máximo de 512 tokens com sobreposição
        Respeita limites de sentenças/parágrafos
        """
        chunks = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        current_chunk = ""
        chunk_num = 0
        
        for sentence in sentences:
            # Verifica se adicionar essa sentença ultrapassa o limite
            test_chunk = current_chunk + " " + sentence if current_chunk else sentence
            token_count = self._tokenize_estimate(test_chunk)
            
            if token_count > self.max_chunk_tokens:
                # Salva chunk anterior se não vazio
                if current_chunk.strip():
                    chunks.append({
                        "id": f"{doc_id}_chunk_{chunk_num}",
                        "doc_id": doc_id,
                        "content": current_chunk.strip(),
                        "tokens": self._tokenize_estimate(current_chunk),
                        "chunk_num": chunk_num
                    })
                    chunk_num += 1
                
                # Começa novo chunk com a sentença atual
                current_chunk = sentence
            else:
                current_chunk = test_chunk
        
        # Adiciona último chunk
        if current_chunk.strip():
            chunks.append({
                "id": f"{doc_id}_chunk_{chunk_num}",
                "doc_id": doc_id,
                "content": current_chunk.strip(),
                "tokens": self._tokenize_estimate(current_chunk),
                "chunk_num": chunk_num
            })
        
        return chunks
    
    def add_document(self, content: str, source: str, doc_type: str = "web", metadata: Dict = None) -> List[str]:
        """
        Adiciona documento ao banco RAG com chunking automático
        
        Args:
            content: Texto do documento
            source: URL ou nome da fonte
            doc_type: Tipo (wikipedia, duckduckgo, outros)
            metadata: Metadata adicional
        
        Returns:
            Lista de IDs de chunks criados
        """
        if not content or not content.strip():
            return []
        
        # Cria ID único do documento
        timestamp = datetime.now().isoformat()
        doc_id = f"{doc_type}_{source.replace('/', '_')}_{int(datetime.now().timestamp())}"
        
        # Divide em chunks
        chunks = self._split_into_chunks(content, doc_id)
        
        # Armazena documento
        doc_record = {
            "id": doc_id,
            "source": source,
            "type": doc_type,
            "created": timestamp,
            "total_chunks": len(chunks),
            "total_tokens": sum(c["tokens"] for c in chunks),
            "metadata": metadata or {}
        }
        
        self.data["documents"].append(doc_record)
        self.data["chunks"].extend(chunks)
        
        # Limpa chunks muito antigos (mantém últimos 100)
        if len(self.data["chunks"]) > 1000:
            self.data["chunks"] = self.data["chunks"][-1000:]
        
        self._save_db()
        
        return [c["id"] for c in chunks]
    
    def _similarity_score(self, query: str, text: str) -> float:
        """
        Calcula score de similitude baseado em:
        - Presença de palavras-chave
        - Overlap de palavras-chave
        - Posição das palavras-chave
        """
        query_lower = query.lower()
        text_lower = text.lower()
        
        # Palavras-chave do query (remove stopwords comuns)
        stopwords = {'o', 'a', 'os', 'as', 'um', 'uma', 'que', 'de', 'para', 'por', 'com', 'em'}
        keywords = [w for w in query_lower.split() if w not in stopwords and len(w) > 2]
        
        if not keywords:
            return 0.0
        
        # Conta ocorrências de keywords
        score = 0.0
        for keyword in keywords:
            occurrences = text_lower.count(keyword)
            score += occurrences * 10  # 10 pontos por ocorrência
        
        # Bonus se a query inteira aparece como substring
        if query_lower in text_lower:
            score += 100
        
        # Normaliza por tamanho do texto
        normalize_factor = max(1, len(text) / 100)
        return score / normalize_factor
    
    def retrieve(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        Recupera os K chunks mais relevantes para a query
        
        Args:
            query: Pergunta/busca do usuário
            top_k: Número de chunks a retornar
        
        Returns:
            Lista de chunks ordenados por relevância
        """
        if not query or not self.data["chunks"]:
            return []
        
        # Calcula score para cada chunk
        scored_chunks = []
        for chunk in self.data["chunks"]:
            score = self._similarity_score(query, chunk["content"])
            if score > 0:  # Inclui apenas chunks com alguma relevância
                scored_chunks.append(({**chunk, "score": score}))
        
        # Ordena por score e retorna top_k
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]
    
    def get_context(self, query: str, max_tokens: int = 1024) -> str:
        """
        Recupera chunks relevantes e os concatena num contexto coerente
        Respeita limite de tokens
        
        Args:
            query: Pergunta/busca
            max_tokens: Máximo de tokens no contexto (default ~4k caracteres)
        
        Returns:
            String de contexto formatado
        """
        chunks = self.retrieve(query, top_k=5)
        if not chunks:
            return ""
        
        context_parts = []
        total_tokens = 0
        max_chars = max_tokens * 3  # Aproximação
        
        for chunk in chunks:
            tokens = chunk["tokens"]
            if total_tokens + tokens > max_tokens:
                break
            
            context_parts.append(chunk["content"])
            total_tokens += tokens
        
        if not context_parts:
            return ""
        
        return "\n\n".join(context_parts)
    
    def clear_old_documents(self, max_age_hours: int = 24):
        """Limpa documentos muito antigos"""
        from datetime import datetime, timedelta
        
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        old_doc_ids = set()
        
        for doc in self.data["documents"]:
            doc_time = datetime.fromisoformat(doc["created"])
            if doc_time < cutoff:
                old_doc_ids.add(doc["id"])
        
        # Remove documentos antigos e seus chunks
        self.data["documents"] = [d for d in self.data["documents"] if d["id"] not in old_doc_ids]
        self.data["chunks"] = [c for c in self.data["chunks"] if c["doc_id"] not in old_doc_ids]
        
        self._save_db()
        return len(old_doc_ids)
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do banco RAG"""
        return {
            "total_documents": len(self.data["documents"]),
            "total_chunks": len(self.data["chunks"]),
            "total_tokens": sum(c["tokens"] for c in self.data["chunks"]),
            "db_type": "local_rag"
        }

# Teste básico
if __name__ == "__main__":
    rag = RAGManager()
    
    # Adiciona documento de teste
    test_doc = """
    A Inteligência Artificial (IA) é a capacidade de máquinas executarem tarefas que normalmente requerem inteligência humana.
    Essas tarefas incluem aprendizado visual, reconhecimento de fala, tomada de decisão e tradução de idiomas.
    
    Existem dois tipos principais de IA: IA Fraca (limitada a tarefas específicas) e IA Forte (geral, como a mente humana).
    A maioria dos sistemas atuais são considerados IA Fraca, como chatbots e assistentes de voz.
    
    O Machine Learning é um subcampo da IA que permite que sistemas aprendam com dados sem serem explicitamente programados.
    Redes neurais artificiais são estruturas inspiradas no cérebro humano usadas em muitos sistemas modernos de IA.
    """
    
    ids = rag.add_document(test_doc, "wikipedia.org", "wikipedia", {"language": "pt-BR"})
    print(f"[RAG] Adicionados {len(ids)} chunks")
    
    # Teste de recuperação
    query = "O que é inteligência artificial?"
    context = rag.get_context(query)
    print(f"\n[RAG] Contexto para '{query}':\n{context}")
    
    # Stats
    stats = rag.get_stats()
    print(f"\n[RAG] Estatísticas: {stats}")
