"""Modo sin API: embeddings léxicos y un vector store en memoria en lugar de OpenAI + Pinecone.

Sirve para correr la evaluación y las pruebas sin keys. Ojo: estos embeddings solo cuentan
palabras en común; un modelo real captura significado (sinónimos, paráfrasis).
"""
import hashlib
import math

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from documentos import cargar_documentos, fragmentar, tokenizar
from rag_system import RAGSystem


class EmbeddingsLexicos(Embeddings):
    """Bolsa de palabras proyectada a 512 dimensiones con un hash."""
    model = "lexico-de-prueba"
    dim = 512

    def _vector(self, texto: str) -> list[float]:
        v = [0.0] * self.dim
        for palabra in tokenizar(texto):
            v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % self.dim] += 1.0
        norma = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norma for x in v]

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in textos]

    def embed_query(self, texto: str) -> list[float]:
        return self._vector(texto)


class VectorStoreEnMemoria(InMemoryVectorStore):
    """InMemoryVectorStore que entiende filtros con la sintaxis de Pinecone ({"campo": {"$eq": valor}})."""

    def _similarity_search_with_score_by_vector(self, embedding, k=4, filter=None):
        if isinstance(filter, dict):
            condiciones = {campo: (v["$eq"] if isinstance(v, dict) else v) for campo, v in filter.items()}
            filter = lambda doc: all(doc.metadata.get(c) == v for c, v in condiciones.items())  # noqa: E731
        return super()._similarity_search_with_score_by_vector(embedding, k, filter)


def sistema_sin_api(fragmentos: list[Document] | None = None) -> RAGSystem:
    fragmentos = fragmentos or fragmentar(cargar_documentos())
    vectorstore = VectorStoreEnMemoria(EmbeddingsLexicos())
    vectorstore.add_documents(fragmentos, ids=[f.id for f in fragmentos])
    return RAGSystem(vectorstore, fragmentos)
