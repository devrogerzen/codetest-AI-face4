"""Setup de Pinecone: verifica si el índice existe y, si no, lo crea en modo Serverless.

Uso:
    python setup_index.py
"""
import logging

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

from config import dimension_embeddings, env, modelo_embeddings, nombre_indice, resumir_error

logger = logging.getLogger("setup")


def _cliente() -> Pinecone:
    return Pinecone(api_key=env("PINECONE_API_KEY", requerida=True))


def preparar_indice():
    """Devuelve el índice listo para usar. Si no existe lo crea; si existe, verifica que su
    dimensión coincida con la del modelo de embeddings."""
    pc = _cliente()
    nombre, dimension = nombre_indice(), dimension_embeddings()
    if pc.has_index(nombre):
        info = pc.describe_index(nombre)
        if info.dimension != dimension:
            raise ValueError(
                f"El índice '{nombre}' tiene dimensión {info.dimension}, pero {modelo_embeddings()} "
                f"genera vectores de {dimension}. Usá otro INDEX_NAME o borrá el índice.")
        logger.info("El índice '%s' ya existe (dimensión %d, métrica %s)", nombre, info.dimension, info.metric)
    else:
        cloud, region = env("PINECONE_CLOUD", "aws"), env("PINECONE_REGION", "us-east-1")
        logger.info("Creando el índice serverless '%s' (%d dimensiones, coseno, %s/%s)...",
                    nombre, dimension, cloud, region)
        pc.create_index(name=nombre, dimension=dimension, metric="cosine",
                        spec=ServerlessSpec(cloud=cloud, region=region))  # espera a que esté listo
        logger.info("Índice creado y listo")
    return pc.Index(nombre)


def conectar_indice():
    """Para consultar: el índice tiene que existir (si no, primero hay que correr la ingesta)."""
    pc, nombre = _cliente(), nombre_indice()
    if not pc.has_index(nombre):
        raise ValueError(f"El índice '{nombre}' no existe. Corré primero: python ingest.py")
    return pc.Index(nombre)


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    try:
        print(preparar_indice().describe_index_stats())
    except Exception as e:  # key faltante o inválida, dimensión incorrecta, sin red...
        print(f"Error de {resumir_error(e)}")
