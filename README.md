# Sistema RAG escalable en la nube con Pinecone

Pre-entrega 4 de AI Engineering (Coderhouse). Lleva el RAG local de la pre-entrega 3 a la nube:
- **Ingesta en Pinecone Serverless**, con metadatos avanzados y subida por lotes.
- **Recuperador híbrido:** BM25 más búsqueda vectorial, fusionados con `EnsembleRetriever`.
- **`evaluate.py`**, que mide **Recall@5**, **Precision@5** y MRR contra un golden set.

## Dataset

En `data/` está la documentación de **Colibrí**, una plataforma de e-commerce **ficticia** (la misma de la pre-entrega 3):

- **4 archivos Markdown:** arquitectura, incidentes, despliegue y seguridad.
- **`faq.json`:** 8 preguntas frecuentes.
- **`metadatos.json`:** la categoría y las etiquetas de cada Markdown.

Cada **sección** de un Markdown y cada **entrada** del FAQ es un documento con un `documento_id` estable, por ejemplo `despliegue.md#despliegue-canary`. En total son 35 documentos.

## Estructura

```
data/              # Markdown + JSON + catálogo de metadatos
config.py          # Variables de entorno, parámetros, embeddings, LLM y namespace
documentos.py      # Carga (Markdown por secciones, JSON por entradas), chunking y metadatos
setup_index.py     # Verifica si el índice existe y lo crea (Serverless)
ingest.py          # Ingesta incremental a Pinecone por lotes
rag_system.py      # RAGSystem: EnsembleRetriever (BM25 + Pinecone) y generación
evaluate.py        # Recall@k, Precision@k y MRR sobre golden_set.json, en 3 modos
golden_set.json    # 10 preguntas con el documento que se espera recuperar
main.py            # Consulta: top-5 documentos + respuesta del modelo
modo_sin_api.py    # Embeddings léxicos + vector store en memoria (para correr sin keys)
prueba_sin_api.py  # Pruebas de carga, ingesta, recuperación y métricas sin keys
```

## Cómo replicar el índice

1. Creá una cuenta gratuita en [pinecone.io](https://www.pinecone.io/) y generá una API key en el panel, en la sección **API Keys**.
2. Cloná el repo y armá el entorno con Python 3.12:
   ```bash
   git clone https://github.com/devrogerzen/codetest-AI-face4.git
   cd codetest-AI-face4
   python -m venv .venv
   .venv\Scripts\activate          # Windows (source .venv/bin/activate en Linux/Mac)
   pip install -r requirements.txt
   ```
3. Configurá las variables. Copiá `.env.example` como `.env` y completá `PINECONE_API_KEY`, `OPENAI_API_KEY` e `INDEX_NAME`.
4. Creá el índice. Si ya existe, el script verifica que su dimensión coincida con la del modelo:
   ```bash
   python setup_index.py
   ```
   Crea un índice **Serverless** (`aws` / `us-east-1`, la región del plan gratuito), con **1536 dimensiones**, que es la de `text-embedding-3-small`, y **métrica coseno**.
5. Subí los documentos:
   ```bash
   python ingest.py               # incremental
   python ingest.py --reiniciar   # vacía el namespace y sube todo
   ```
6. Evaluá y consultá:
   ```bash
   python evaluate.py
   python main.py "¿Qué hago si se cae Redis?"
   python main.py "¿Cada cuánto se rotan los secretos?" --categoria seguridad
   ```

Para probar todo **sin keys**:
```bash
python prueba_sin_api.py
python evaluate.py --sin-api
python main.py "¿Qué hago si se cae Redis?" --sin-api
```

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `PINECONE_API_KEY` | **Sí** | API key de Pinecone |
| `INDEX_NAME` | **Sí** | Nombre del índice, por ejemplo `colibri` |
| `OPENAI_API_KEY` | **Sí** | Embeddings (`text-embedding-3-small`) y, por defecto, el LLM |
| `PINECONE_NAMESPACE` | No | Default `colibri-docs` |
| `PINECONE_CLOUD` / `PINECONE_REGION` | No | Defaults `aws` / `us-east-1` |
| `EMBEDDINGS_MODEL` | No | Default `text-embedding-3-small` (con otro modelo, ajustar la dimensión) |
| `LLM_PROVIDER` | No | `openai` (default) o `anthropic`, para `main.py` |
| `ANTHROPIC_API_KEY` | Si `LLM_PROVIDER=anthropic` | API key de Anthropic |

## Ingesta: metadatos y escalabilidad

Cada vector se sube con estos metadatos:

| Campo | Ejemplo | Para qué sirve |
|---|---|---|
| `text` | el contenido del fragmento | El texto **original** viaja en los metadatos, así que no hace falta otra base de datos para recuperarlo |
| `documento_id` | `despliegue.md#despliegue-canary` | Identifica el documento; es la unidad que mide la evaluación |
| `fuente` | `despliegue.md` | Archivo de origen, para citar la fuente |
| `pagina` | `4` | Página (en Markdown, el número de sección) |
| `categoria` | `devops` | Permite **filtrar** las búsquedas (`--categoria`) |
| `etiquetas` | `["ci-cd", "canary"]` | Etiquetas temáticas |
| `titulo` / `seccion` | `Proceso de despliegue` / `Despliegue canary` | Contexto legible |
| `tipo` | `markdown` o `faq` | Formato de origen |
| `chunk_id` / `fragmento` | `despliegue.md#despliegue-canary::0` | Identifica el fragmento; el `EnsembleRetriever` lo usa para fusionar |

- **Chunking:** 600 tokens con 60 de overlap, dentro del rango recomendado de 500 a 800. Primero se corta por secciones (`MarkdownHeaderTextSplitter`) y después por tokens.
- **Subida por lotes** de 100 vectores (`BATCH_SIZE`).
- **Namespace** propio (`colibri-docs`), para no mezclarse con otros datos del mismo índice.
- **Ingesta incremental:** el ID de cada vector es un hash de su contenido. Solo se suben los fragmentos nuevos o modificados, y se borran los que ya no existen.
- **Dimensión verificada:** si el índice existe con otra dimensión, `setup_index.py` frena con un error claro en vez de fallar al subir.

## Recuperador híbrido (`RAGSystem`)

```
consulta ──► BM25 (palabras exactas, en memoria) ─────┐
        └──► Pinecone (significado, embeddings) ──────┤──► EnsembleRetriever (RRF) ──► top-5
```

- **BM25** encuentra términos exactos: `pagos_modo_cola`, `X-Colibri-Trace-Id`, `429`, comandos. Usa un tokenizador propio: minúsculas, sin acentos, sin palabras vacías y conservando los `_`.
- **La búsqueda vectorial** encuentra paráfrasis: "pegar una contraseña en un chat" encuentra la sección sobre secretos filtrados.
- **`EnsembleRetriever`** fusiona las dos listas con **Reciprocal Rank Fusion**, con pesos 0.5 y 0.5. Combina **posiciones**, no puntajes, porque los puntajes de BM25 y del coseno tienen escalas distintas. `id_key="chunk_id"` evita que el mismo fragmento aparezca dos veces.
- **Filtro por categoría:** en Pinecone se aplica dentro de la búsqueda (`{"categoria": {"$eq": ...}}`) y en BM25 sobre el subconjunto de esa categoría.
- **`responder()`** completa el flujo RAG: recuperación híbrida más generación anclada en el contexto, que dice "No lo sé." si la respuesta no está.

## Evaluación (`evaluate.py`)

`golden_set.json` tiene 10 preguntas con el formato `{"pregunta": ..., "documento_id_esperado": ...}`. En 3 de las preguntas hay dos documentos relevantes, así que el campo es una lista. Hay preguntas con **términos exactos**, donde gana BM25, y con **paráfrasis**, donde ganan los vectores. El script corre las preguntas de forma concurrente, con `asyncio.gather` y un `Semaphore(4)`, en tres modos: solo vectores, solo BM25 e híbrido.

- **Recall@5:** qué parte de los documentos relevantes aparece entre los 5 recuperados.
- **Precision@5:** qué parte de los 5 recuperados es relevante. Con un solo documento relevante por pregunta, el máximo posible es 0.20.
- **MRR:** 1 dividido por la posición del primer resultado relevante, promediado entre las preguntas.

### Resultados

Corrida con `python evaluate.py --sin-api` (embeddings léxicos en memoria):

| Modo | Recall@5 | Precision@5 | MRR |
|---|---|---|---|
| Solo vectores (léxicos) | 0.90 | 0.22 | 1.00 |
| Solo BM25 | 0.95 | 0.24 | 1.00 |
| **Híbrido** | **0.95** | **0.24** | **1.00** |

Con embeddings léxicos, los dos recuperadores "ven" lo mismo: palabras en común. Con `text-embedding-3-small` en Pinecone, la parte vectorial capta paráfrasis y la diferencia entre modos se vuelve más visible. Para reproducirlo, corré `python evaluate.py` con las keys configuradas.

## Pruebas sin API key

`prueba_sin_api.py` reemplaza a Pinecone por un vector store en memoria y verifica 15 cosas:
- **Documentos:** IDs únicos, metadatos completos, documentos Markdown y JSON, fragmentos de 600 tokens o menos, IDs deterministas.
- **Golden set:** que todos sus IDs existan.
- **Ingesta incremental:** que la primera subida suba todo, que la segunda no suba nada y que al borrar un documento se borren sus vectores.
- **Recuperador:** que BM25 encuentre un término exacto, que el top-5 no repita fragmentos y que el filtro por categoría se aplique.
- **Métricas:** que el cálculo de las métricas sea correcto.
