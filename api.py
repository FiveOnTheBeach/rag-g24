"""API de questions/réponses sur l'histoire (RAG + Ollama).

Lancement :
    uvicorn api:app --reload
Swagger : http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


import config
import rag
import json

from fastapi import UploadFile, File, Form
import tempfile
from photo_vers_texte import analyser_photo, construire_question

SYSTEM_PROMPT = """Tu es le moteur d'analyse de Givaudan Scent Journey. Tu ne dialogues jamais avec l'utilisateur et tu ne poses aucune question.
Tu reçois un récit (texte, voix transcrite, description de photo, images choisies, produit visé).
En t'appuyant UNIQUEMENT sur le contexte fourni, réponds par un JSON valide, sans texte autour :
{
 "comprehension": {"lieu": "", "moment": "", "meteo": "", "emotion": "", "elements": []},
 "signature": {"nom": "", "description": ""},
 "roue": [{"famille": "", "pourcentage": 0}],
 "profil": {
   "tete": [{"ingredient": "", "reference": "", "raison": "", "sources": []}],
   "coeur": [{"ingredient": "", "reference": "", "raison": "", "sources": []}],
   "fond": [{"ingredient": "", "reference": "", "raison": "", "sources": []}]
 },
 "limites_catalogue": [],
 "informations_manquantes": [],
 "brief": ""
}
Règles : n'utilise que des ingrédients et références présents dans le contexte, n'invente aucune source, les pourcentages de la roue font 100. Si le récit est vague, propose le profil le plus probable et remplis "informations_manquantes".
Les familles de la roue doivent être exactement celles du catalogue : Floral, Fruity, Citrus, Herbal - Agrestic, Woody, Green, Ambery, Spicy, Musky, Leather - Moss, Gourmand, Aldehydic, Marine. Aucune autre."""

app = FastAPI(
    title="Story RAG API",
    description="Pose des questions sur l'histoire chargée dans la base vectorielle. "
                "Les réponses sont générées par un LLM Ollama à partir des passages retrouvés.",
    version="1.0.0",
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["Comment s'appelle le cheval de Loran ?"])
    top_k: int = Field(config.TOP_K, ge=1, le=20, description="Nombre de passages à retrouver")


class Source(BaseModel):
    chapter: str
    text: str
    score: float = Field(description="Similarité cosinus (1 = identique)")


class AskResponse(BaseModel):
    question: str
    answer: dict | str
    model: str
    sources: list[Source]


def retrieve(question: str, top_k: int) -> list[Source]:
    collection = rag.get_collection()
    if collection.count() == 0:
        raise HTTPException(503, "La base est vide : lance d'abord `python ingest.py`.")
    result = collection.query(
        query_embeddings=[rag.embed_query(question)],
        n_results=min(top_k, collection.count()),
    )
    return [
        Source(chapter=meta["chapter"], text=doc, score=round(1 - dist, 4))
        for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
    ]


@app.get("/health", tags=["système"])
def health():
    """Vérifie que la base est chargée et indique les modèles utilisés."""
    return {
        "chunks": rag.get_collection().count(),
        "llm_model": config.LLM_MODEL,
        "embed_model": config.EMBED_MODEL,
    }


@app.post("/search", response_model=list[Source], tags=["histoire"])
def search(req: AskRequest):
    """Retourne seulement les passages pertinents (sans appeler le LLM)."""
    return retrieve(req.question, req.top_k)


@app.post("/ask", response_model=AskResponse, tags=["histoire"])
def ask(req: AskRequest):
    """Répond à une question sur l'histoire à partir des passages retrouvés."""
    sources = retrieve(req.question, req.top_k)
    context = "\n\n---\n\n".join(f"[{s.chapter}]\n{s.text}" for s in sources)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Extraits de la base Scent Journey :\n\n{context}\n\nQuestion : {req.question}"},
    ]
    try:
        answer = rag.chat(messages)
    except Exception as exc:  # Ollama injoignable, modèle absent...
        raise HTTPException(502, f"Erreur Ollama : {exc}") from exc
    cleaned = answer.strip().strip("`").removeprefix("json").strip()
    try:
        answer = json.loads(cleaned)
    except json.JSONDecodeError:
        answer = cleaned
    return AskResponse(question=req.question, answer=answer, model=config.LLM_MODEL, sources=sources)

@app.post("/ask_photo")
async def ask_photo(photo: UploadFile = File(...), recit: str = Form("")):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(await photo.read())
        chemin = tmp.name
    description = analyser_photo(chemin)
    question = construire_question(description, recit)
    reponse = ask(AskRequest(question=question))
    return {"description_photo": description, "resultat": reponse}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
