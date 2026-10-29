"""Ingesta a Pinecone: carga /data, fragmenta, genera embeddings y sube por lotes con metadatos.

Es incremental: solo se suben los fragmentos nuevos o modificados y se borran los obsoletos.

Uso:
    python ingest.py               # sincroniza el namespace con la carpeta data/
    python ingest.py --reiniciar   # vacía el namespace y sube todo de cero
"""
import argparse
import logging

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_pinecone import PineconeVectorStore

from config import BATCH_SIZE, crear_embeddings, namespace, resumir_error
from documentos import cargar_documentos, fragmentar
from setup_index import preparar_indice

logger = logging.getLogger("ingesta")


def sincronizar(indice, vectorstore: VectorStore, fragmentos: list[Document], ns: str) -> dict[str, int]:
    """Deja el namespace igual a los fragmentos actuales, sin volver a subir lo que no cambió."""
    actuales = {f.id: f for f in fragmentos}
    existentes = {id_ for pagina in indice.list(namespace=ns) for id_ in pagina}

    nuevos = [f for id_, f in actuales.items() if id_ not in existentes]
    obsoletos = sorted(existentes - actuales.keys())
    for i in range(0, len(obsoletos), 1000):
        indice.delete(ids=obsoletos[i:i + 1000], namespace=ns)
    if nuevos:
        # El texto original viaja en los metadatos (text_key="text"): al buscar no hace falta
        # consultar otra base de datos para recuperarlo
        vectorstore.add_documents(nuevos, ids=[f.id for f in nuevos], batch_size=BATCH_SIZE)

    resumen = {"fragmentos": len(fragmentos), "subidos": len(nuevos), "borrados": len(obsoletos),
               "sin_cambios": len(fragmentos) - len(nuevos)}
    logger.info("Namespace '%s': %d subidos, %d borrados, %d sin cambios", ns,
                resumen["subidos"], resumen["borrados"], resumen["sin_cambios"])
    return resumen


def main(reiniciar: bool = False) -> dict[str, int]:
    indice, ns = preparar_indice(), namespace()
    if reiniciar:
        try:
            indice.delete(delete_all=True, namespace=ns)
            logger.info("Namespace '%s' vaciado", ns)
        except Exception as e:  # el namespace todavía no existe
            logger.info("No había nada que borrar en '%s' (%s)", ns, type(e).__name__)
    vectorstore = PineconeVectorStore(index=indice, embedding=crear_embeddings(), namespace=ns)
    return sincronizar(indice, vectorstore, fragmentar(cargar_documentos()), ns)


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
    for ruido in ("httpx", "httpx2"):
        logging.getLogger(ruido).setLevel(logging.WARNING)
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--reiniciar", action="store_true", help="vacía el namespace y sube todo")
    try:
        print(main(argumentos.parse_args().reiniciar))
        print("Nota: Pinecone tarda unos segundos en reflejar los cambios en las búsquedas.")
    except Exception as e:  # key faltante o inválida, dimensión incorrecta, sin red...
        print(f"Error de {resumir_error(e)}")
