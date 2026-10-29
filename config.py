"""Configuración compartida: variables de entorno, parámetros, embeddings, LLM y Pinecone."""
import os
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
GOLDEN_SET = BASE / "golden_set.json"

CHUNK_TOKENS = 600    # punto medio recomendado: ~500-800 tokens
OVERLAP_TOKENS = 60
TOP_K = 5             # documentos que devuelve el recuperador (y k de las métricas)
BATCH_SIZE = 100      # vectores por lote al subir a Pinecone (100-200 es el punto dulce)

# La dimensión del índice tiene que coincidir con la del modelo de embeddings
DIMENSIONES = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072,
               "text-embedding-ada-002": 1536}


def env(nombre: str, default: str | None = None, requerida: bool = False) -> str | None:
    valor = os.getenv(nombre) or default
    if requerida and not valor:
        raise ValueError(f"Falta {nombre} en el .env")
    return valor


def resumir_error(e: Exception) -> str:
    """Una línea legible: los errores de Pinecone traen los headers HTTP completos."""
    lineas = [linea.strip() for linea in str(e).splitlines() if linea.strip()][:2]
    return f"{type(e).__name__}: {' '.join(lineas)[:250]}"


def modelo_embeddings() -> str:
    return env("EMBEDDINGS_MODEL", "text-embedding-3-small")


def dimension_embeddings() -> int:
    modelo = modelo_embeddings()
    if modelo in DIMENSIONES:
        return DIMENSIONES[modelo]
    return int(env("EMBEDDINGS_DIM", requerida=True))  # para modelos que no están en la tabla


def crear_embeddings() -> Embeddings:
    env("OPENAI_API_KEY", requerida=True)
    return OpenAIEmbeddings(model=modelo_embeddings())


def crear_llm() -> BaseChatModel:
    """Elige ChatOpenAI o ChatAnthropic según LLM_PROVIDER (la misma idea que el Módulo 1)."""
    provider = env("LLM_PROVIDER", "openai").lower()
    if provider == "openai":
        env("OPENAI_API_KEY", requerida=True)
        return ChatOpenAI(model=env("OPENAI_MODEL", "gpt-4o-mini"), temperature=0,
                          timeout=30, max_retries=2)
    if provider == "anthropic":
        env("ANTHROPIC_API_KEY", requerida=True)
        # Sin temperature: el SDK actual de Anthropic ya no la acepta
        return ChatAnthropic(model=env("ANTHROPIC_MODEL", "claude-haiku-4-5"),
                             max_tokens=1024, timeout=30, max_retries=2)
    raise ValueError(f"LLM_PROVIDER no soportado: {provider!r} (usá openai o anthropic)")


def nombre_indice() -> str:
    return env("INDEX_NAME", requerida=True)


def namespace() -> str:
    # Separa los datos dentro del índice (por cliente, por entorno, por tipo de documento...)
    return env("PINECONE_NAMESPACE", "colibri-docs")
