"""Evaluación del recuperador con el golden set: Recall@k, Precision@k y MRR.

Compara los tres modos (solo vectores, solo BM25 e híbrido) sobre las mismas preguntas.

Uso:
    python evaluate.py             # contra Pinecone (necesita las keys del .env)
    python evaluate.py --sin-api   # embeddings léxicos en memoria, sin keys
"""
import argparse
import asyncio
import json
import logging

from dotenv import load_dotenv

from config import GOLDEN_SET, TOP_K, resumir_error
from rag_system import MODOS, RAGSystem


def relevantes(caso: dict) -> set[str]:
    esperado = caso["documento_id_esperado"]
    return {esperado} if isinstance(esperado, str) else set(esperado)


def metricas(recuperados: list[str], relevantes: set[str], k: int = TOP_K) -> dict[str, float]:
    """recuperados: documento_id de cada uno de los top-k resultados, en orden."""
    top = recuperados[:k]
    # Recall@k: qué parte de los documentos relevantes apareció en el top-k
    recall = len(relevantes & set(top)) / len(relevantes)
    # Precision@k: qué parte del top-k es realmente útil
    precision = sum(doc in relevantes for doc in top) / k
    # MRR: 1 / posición del primer resultado relevante (1 si sale primero, 0.5 si segundo...)
    posicion = next((i for i, doc in enumerate(top, 1) if doc in relevantes), None)
    return {"recall": recall, "precision": precision, "rr": 1 / posicion if posicion else 0.0,
            "posicion": posicion}


async def evaluar(sistema: RAGSystem, casos: list[dict], concurrencia: int = 4) -> dict[str, list[dict]]:
    """Corre todas las preguntas en los tres modos, como mucho `concurrencia` a la vez."""
    semaforo = asyncio.Semaphore(concurrencia)  # no saturar las APIs (evita el 429)

    async def uno(modo: str, caso: dict) -> dict:
        async with semaforo:
            docs = await sistema.buscar(caso["pregunta"], modo=modo)
        ids = [d.metadata["documento_id"] for d in docs]
        return {"modo": modo, "pregunta": caso["pregunta"], "recuperados": ids,
                **metricas(ids, relevantes(caso), sistema.k)}

    filas = await asyncio.gather(*(uno(modo, caso) for modo in MODOS for caso in casos))
    return {modo: [f for f in filas if f["modo"] == modo] for modo in MODOS}


def promedio(filas: list[dict], clave: str) -> float:
    return sum(f[clave] for f in filas) / len(filas)


def reporte(resultados: dict[str, list[dict]], k: int = TOP_K) -> None:
    print(f"\nDetalle del modo híbrido (top-{k}):\n")
    print(f"{'':3} {'pos':>3}  {'P@' + str(k):>5}  pregunta")
    for f in resultados["hibrido"]:
        marca = "OK " if f["recall"] > 0 else "-- "
        print(f"{marca} {f['posicion'] or '-':>3}  {f['precision']:>5.2f}  {f['pregunta']}")

    print(f"\nResumen ({len(resultados['hibrido'])} preguntas):\n")
    print(f"{'modo':<10} {'Recall@' + str(k):>9} {'Precision@' + str(k):>12} {'MRR':>6}")
    for modo, filas in resultados.items():
        print(f"{modo:<10} {promedio(filas, 'recall'):>9.2f} {promedio(filas, 'precision'):>12.2f} "
              f"{promedio(filas, 'rr'):>6.2f}")
    print(f"\nNota: con un solo documento relevante por pregunta, Precision@{k} no puede superar "
          f"{1 / k:.2f}; el máximo depende de cuántos relevantes tenga cada pregunta.")


async def main(sin_api: bool) -> None:
    if sin_api:
        from modo_sin_api import sistema_sin_api
        sistema = sistema_sin_api()
        print("Modo sin API: embeddings léxicos en memoria (no son los resultados de Pinecone).")
    else:
        sistema = RAGSystem.desde_pinecone()
    casos = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    reporte(await evaluar(sistema, casos), sistema.k)


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s")
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--sin-api", action="store_true", help="evalúa sin keys, en memoria")
    try:
        asyncio.run(main(argumentos.parse_args().sin_api))
    except Exception as e:  # key faltante o inválida, índice inexistente, sin red...
        print(f"Error de {resumir_error(e)}")
