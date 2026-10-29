"""Prueba sin API key de la carga de documentos, la ingesta incremental, el recuperador híbrido
y las métricas. Pinecone se reemplaza por un vector store en memoria.

Uso:
    python prueba_sin_api.py
"""
import asyncio
import json

import tiktoken

from config import CHUNK_TOKENS, GOLDEN_SET
from documentos import cargar_documentos, fragmentar
from evaluate import evaluar, metricas, relevantes
from ingest import sincronizar
from modo_sin_api import EmbeddingsLexicos, VectorStoreEnMemoria, sistema_sin_api

resultados: list[bool] = []


def chequear(descripcion: str, condicion: bool, detalle: str = "") -> None:
    resultados.append(condicion)
    print(f"  {'OK   ' if condicion else 'FALLA'} {descripcion}{f'  ({detalle})' if detalle else ''}")


class IndiceFalso:
    """Imita la parte del índice de Pinecone que usa la ingesta (list y delete)."""
    def __init__(self, vectorstore: VectorStoreEnMemoria):
        self.vectorstore = vectorstore

    # Sin anotaciones de tipo: dentro de la clase, "list" ya es este método y no el de Python
    def list(self, namespace):
        yield [*self.vectorstore.store.keys()]

    def delete(self, ids, namespace):
        self.vectorstore.delete(ids)


async def main() -> None:
    print("\n> Documentos y chunking")
    documentos = cargar_documentos()
    fragmentos = fragmentar(documentos)
    ids_docs = [d.metadata["documento_id"] for d in documentos]
    chequear("cada sección y cada entrada del FAQ tiene un documento_id único",
             len(ids_docs) == len(set(ids_docs)), f"{len(ids_docs)} documentos")
    campos = {"documento_id", "fuente", "pagina", "categoria", "etiquetas", "chunk_id", "fragmento"}
    chequear("cada fragmento lleva los metadatos avanzados", all(campos <= f.metadata.keys() for f in fragmentos))
    chequear("hay documentos Markdown y JSON",
             {f.metadata["tipo"] for f in fragmentos} == {"markdown", "faq"})
    enc = tiktoken.get_encoding("cl100k_base")
    maximo = max(len(enc.encode(f.page_content)) for f in fragmentos)
    chequear(f"ningún fragmento supera los {CHUNK_TOKENS} tokens", maximo <= CHUNK_TOKENS, f"máximo {maximo}")
    chequear("los IDs de los fragmentos son deterministas",
             [f.id for f in fragmentos] == [f.id for f in fragmentar(cargar_documentos())])

    casos = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    faltantes = [i for c in casos for i in relevantes(c) if i not in set(ids_docs)]
    chequear("todos los documento_id del golden set existen", not faltantes, str(faltantes or len(casos)))

    print("\n> Ingesta incremental (Pinecone simulado en memoria)")
    vectorstore = VectorStoreEnMemoria(EmbeddingsLexicos())
    indice = IndiceFalso(vectorstore)
    r = sincronizar(indice, vectorstore, fragmentos, "pruebas")
    chequear("la primera ingesta sube todo", r["subidos"] == len(fragmentos))
    r = sincronizar(indice, vectorstore, fragmentos, "pruebas")
    chequear("la segunda ingesta no sube nada", r["subidos"] == r["borrados"] == 0)
    modificados = fragmentar(documentos[:-1])  # como si se hubiera borrado la última entrada del FAQ
    r = sincronizar(indice, vectorstore, modificados, "pruebas")
    chequear("si se borra un documento, se borran sus vectores", r["borrados"] == 1 and r["subidos"] == 0)

    print("\n> Recuperador híbrido")
    sistema = sistema_sin_api(fragmentos)
    docs = await sistema.buscar("pagos_modo_cola")
    chequear("BM25 encuentra un término técnico exacto",
             docs[0].metadata["documento_id"] == "guia_incidentes.md#runbook-errores-5xx-en-pagos",
             docs[0].metadata["documento_id"])
    docs = await sistema.buscar("¿Qué hago si se cae Redis?")
    chunk_ids = [d.metadata["chunk_id"] for d in docs]
    chequear("el híbrido devuelve top-5 sin fragmentos repetidos", len(docs) == 5 == len(set(chunk_ids)))
    docs = await sistema.buscar("¿Cada cuánto se rotan los secretos?", categoria="seguridad")
    chequear("el filtro por categoría se aplica en BM25 y en vectores",
             {d.metadata["categoria"] for d in docs} == {"seguridad"})

    print("\n> Métricas")
    m = metricas(["a", "x", "b", "y", "z"], {"a", "b"})
    chequear("Recall@5, Precision@5 y MRR se calculan bien",
             (m["recall"], m["precision"], m["rr"]) == (1.0, 0.4, 1.0), str(m))
    m = metricas(["x", "y", "a", "z", "w"], {"a"})
    chequear("MRR con el relevante en la posición 3 es 1/3", round(m["rr"], 3) == 0.333 and m["recall"] == 1.0)
    evaluacion = await evaluar(sistema, casos)
    chequear("la evaluación corre los 3 modos sobre todo el golden set",
             all(len(filas) == len(casos) for filas in evaluacion.values()))

    print(f"\n{sum(resultados)}/{len(resultados)} chequeos correctos")
    raise SystemExit(0 if all(resultados) else 1)


if __name__ == "__main__":
    asyncio.run(main())
