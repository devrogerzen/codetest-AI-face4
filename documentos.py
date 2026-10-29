"""Carga de documentos (Markdown y JSON), chunking y metadatos.

Cada sección de un Markdown y cada entrada de un JSON es un "documento" con un documento_id
estable (por ejemplo "despliegue.md#despliegue-canary"): es la unidad que evalúa el golden set.
"""
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from config import CHUNK_TOKENS, DATA_DIR, OVERLAP_TOKENS

CATALOGO = "metadatos.json"  # categoría y etiquetas de cada archivo Markdown

STOPWORDS = set("""a al algo como con cual cuales cuando de del el ella en entre es esa ese eso esta
este esto hay la las le lo los mas me mi no o para pero por que se si sin sobre su sus te tu un una
uno unos y ya hace hacer hago puedo""".split())


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def slug(texto: str) -> str:
    """"Runbook: Redis caído" -> "runbook-redis-caido" (IDs legibles y solo ASCII)."""
    return re.sub(r"[^a-z0-9]+", "-", _sin_acentos(texto.lower())).strip("-")


def tokenizar(texto: str) -> list[str]:
    """Tokenizador para BM25: minúsculas, sin acentos y sin palabras vacías. Conserva los guiones
    bajos para que términos como pagos_modo_cola sigan siendo una sola palabra."""
    return [t for t in re.findall(r"[a-z0-9_]+", _sin_acentos(texto.lower())) if t not in STOPWORDS]


def cargar_documentos(directorio: Path = DATA_DIR) -> list[Document]:
    """Un Document por sección de Markdown o por entrada de JSON, con metadatos enriquecidos."""
    catalogo = json.loads((directorio / CATALOGO).read_text(encoding="utf-8"))
    por_secciones = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "titulo"), ("##", "seccion")], strip_headers=False)
    documentos = []

    for archivo in sorted(directorio.glob("*.md")):
        info = catalogo.get(archivo.name, {})
        for pagina, seccion in enumerate(por_secciones.split_text(archivo.read_text(encoding="utf-8")), 1):
            nombre = seccion.metadata.get("seccion", "Introducción")
            documentos.append(Document(page_content=seccion.page_content, metadata={
                "documento_id": f"{archivo.name}#{slug(nombre)}",
                "fuente": archivo.name,
                "titulo": seccion.metadata.get("titulo", archivo.stem),
                "seccion": nombre,
                "pagina": pagina,  # en Markdown, cada sección cuenta como una página
                "categoria": info.get("categoria", "general"),
                "etiquetas": info.get("etiquetas", []),
                "tipo": "markdown",
            }))

    for archivo in sorted(p for p in directorio.glob("*.json") if p.name != CATALOGO):
        for pagina, entrada in enumerate(json.loads(archivo.read_text(encoding="utf-8")), 1):
            documentos.append(Document(
                page_content=f"Pregunta: {entrada['pregunta']}\nRespuesta: {entrada['respuesta']}",
                metadata={
                    "documento_id": f"{archivo.name}#{entrada['id']}",
                    "fuente": archivo.name,
                    "titulo": "Preguntas frecuentes",
                    "seccion": entrada["pregunta"],
                    "pagina": pagina,
                    "categoria": entrada.get("categoria", "general"),
                    "etiquetas": entrada.get("etiquetas", []),
                    "tipo": "faq",
                }))

    if not documentos:
        raise FileNotFoundError(f"No hay documentos en {directorio}")
    return documentos


def fragmentar(documentos: list[Document]) -> list[Document]:
    """Corta cada documento en fragmentos de hasta CHUNK_TOKENS tokens. Cada fragmento hereda
    los metadatos de su documento y recibe un ID determinista (hash del contenido)."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=CHUNK_TOKENS, chunk_overlap=OVERLAP_TOKENS)
    fragmentos = []
    for doc in documentos:
        documento_id = doc.metadata["documento_id"]
        for i, texto in enumerate(splitter.split_text(doc.page_content)):
            huella = hashlib.sha256(f"{documento_id}|{i}|{texto}".encode()).hexdigest()[:16]
            fragmentos.append(Document(id=huella, page_content=texto, metadata={
                **doc.metadata, "fragmento": i, "chunk_id": f"{documento_id}::{i}"}))
    return fragmentos
