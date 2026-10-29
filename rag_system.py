"""RAGSystem: recuperador híbrido que combina búsqueda léxica (BM25) y semántica (Pinecone)."""
import logging

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from langchain_pinecone import PineconeVectorStore
from pydantic import BaseModel

from config import TOP_K, crear_embeddings, namespace
from documentos import cargar_documentos, fragmentar, tokenizar

logger = logging.getLogger("rag")

MODOS = ("vectorial", "bm25", "hibrido")


class Respuesta(BaseModel):
    pregunta: str
    respuesta: str
    fuentes: list[str]  # documento_id de los fragmentos que se le pasaron al modelo


PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Sos el asistente técnico de la plataforma Colibrí. Respondé SOLO con la "
               "información del CONTEXTO. Si no alcanza, respondé exactamente \"No lo sé.\". "
               "Al final citá entre corchetes los documento_id que usaste."),
    ("human", "CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"),
])


class RAGSystem:
    """Encapsula el EnsembleRetriever: BM25 (palabras exactas) + vectores (significado),
    fusionados con Reciprocal Rank Fusion. Devuelve los top-k documentos."""

    def __init__(self, vectorstore: VectorStore, fragmentos: list[Document], k: int = TOP_K,
                 pesos: tuple[float, float] = (0.5, 0.5)):
        self.vectorstore = vectorstore
        self.fragmentos = fragmentos  # BM25 vive en memoria: necesita el texto de los fragmentos
        self.k = k
        self.pesos = pesos
        self._bm25: dict[str | None, BM25Retriever] = {}

    @classmethod
    def desde_pinecone(cls, **kwargs) -> "RAGSystem":
        from setup_index import conectar_indice
        vectorstore = PineconeVectorStore(index=conectar_indice(), embedding=crear_embeddings(),
                                          namespace=namespace())
        # Los mismos fragmentos (mismos IDs) que subió la ingesta
        return cls(vectorstore, fragmentar(cargar_documentos()), **kwargs)

    def _bm25_retriever(self, categoria: str | None) -> BM25Retriever:
        if categoria not in self._bm25:
            docs = [f for f in self.fragmentos if categoria is None or f.metadata["categoria"] == categoria]
            if not docs:
                raise ValueError(f"No hay documentos con la categoría {categoria!r}")
            self._bm25[categoria] = BM25Retriever.from_documents(docs, k=self.k, preprocess_func=tokenizar)
        return self._bm25[categoria]

    def _vectorial_retriever(self, categoria: str | None) -> BaseRetriever:
        busqueda = {"k": self.k}
        if categoria:
            # Filtro de metadatos con la sintaxis de Pinecone: se aplica DENTRO de la búsqueda
            busqueda["filter"] = {"categoria": {"$eq": categoria}}
        return self.vectorstore.as_retriever(search_kwargs=busqueda)

    def retriever(self, modo: str = "hibrido", categoria: str | None = None) -> BaseRetriever:
        if modo == "bm25":
            return self._bm25_retriever(categoria)
        if modo == "vectorial":
            return self._vectorial_retriever(categoria)
        if modo == "hibrido":
            # id_key: dos resultados con el mismo chunk_id son el mismo fragmento (se fusionan)
            return EnsembleRetriever(
                retrievers=[self._bm25_retriever(categoria), self._vectorial_retriever(categoria)],
                weights=list(self.pesos), id_key="chunk_id")
        raise ValueError(f"Modo desconocido: {modo!r} (opciones: {', '.join(MODOS)})")

    async def buscar(self, consulta: str, modo: str = "hibrido", categoria: str | None = None) -> list[Document]:
        """Devuelve los top-k fragmentos para la consulta."""
        docs = (await self.retriever(modo, categoria).ainvoke(consulta))[: self.k]
        logger.info("[%s] %s -> %s", modo, consulta, [d.metadata["documento_id"] for d in docs])
        return docs

    async def responder(self, consulta: str, llm: BaseChatModel, categoria: str | None = None) -> Respuesta:
        """Flujo RAG completo: recuperación híbrida + generación anclada en el contexto."""
        docs = await self.buscar(consulta, categoria=categoria)
        contexto = "\n\n---\n\n".join(f"[{d.metadata['documento_id']}]\n{d.page_content}" for d in docs)
        texto = await (PROMPT | llm | StrOutputParser()).ainvoke({"contexto": contexto, "pregunta": consulta})
        return Respuesta(pregunta=consulta, respuesta=texto,
                         fuentes=list(dict.fromkeys(d.metadata["documento_id"] for d in docs)))
