"""Consulta al sistema RAG híbrido: muestra los top-5 documentos y la respuesta del modelo.

Uso:
    python main.py "¿Qué hago si se cae Redis?"
    python main.py "¿Cada cuánto se rotan los secretos?" --categoria seguridad
    python main.py "¿Qué hago si se cae Redis?" --sin-api      # solo recuperación, sin keys
"""
import argparse
import asyncio
import logging

from dotenv import load_dotenv

from config import crear_llm, resumir_error
from rag_system import RAGSystem


async def main(pregunta: str, categoria: str | None, sin_api: bool) -> None:
    if sin_api:
        from modo_sin_api import sistema_sin_api
        sistema = sistema_sin_api()
    else:
        sistema = RAGSystem.desde_pinecone()

    docs = await sistema.buscar(pregunta, categoria=categoria)
    print(f"\nTop-{sistema.k} (híbrido{f', categoría {categoria}' if categoria else ''}):\n")
    for i, d in enumerate(docs, 1):
        m = d.metadata
        print(f"{i}. {m['documento_id']}  [{m['categoria']}] {m['fuente']} p.{m['pagina']}  "
              f"etiquetas={m['etiquetas']}")

    if not sin_api:
        respuesta = await sistema.responder(pregunta, crear_llm(), categoria=categoria)
        print(f"\n{respuesta.model_dump_json(indent=2)}")


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s")
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("pregunta")
    argumentos.add_argument("--categoria", help="arquitectura, operaciones, devops o seguridad")
    argumentos.add_argument("--sin-api", action="store_true", help="solo recuperación, sin keys")
    a = argumentos.parse_args()
    try:
        asyncio.run(main(a.pregunta, a.categoria, a.sin_api))
    except Exception as e:  # key faltante o inválida, índice inexistente, sin red...
        print(f"Error de {resumir_error(e)}")
