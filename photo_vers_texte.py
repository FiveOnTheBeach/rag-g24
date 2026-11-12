"""Transforme une photo en description texte pour le RAG Scent Journey.

Usage (dans le terminal, dossier rag-g24, venv activé) :
    python photo_vers_texte.py ma_photo.jpg "J'étais triste ce jour-là"

Pré-requis :
    pip install ollama
    ollama pull qwen2.5vl:7b      (ou un autre modèle avec la capacité "vision")
"""
import json
import sys
import urllib.request

import ollama

VISION_MODEL = "qwen2.5vl:7b"   # vérifier avec : ollama show <modele>  -> ligne "vision"

PROMPT = """Tu analyses une photo de souvenir pour aider à créer un parfum.
Décris UNIQUEMENT ce que tu vois, sans inventer. Réponds en JSON avec ces clés :
"lieu" (ex : plage, temple, forêt, rue de ville, cuisine),
"pays_ou_culture_visible" (seulement si c'est évident, sinon "inconnu"),
"moment" (matin, soir, nuit, inconnu),
"meteo" (soleil, pluie, après la pluie, neige, inconnu),
"elements_visibles" (liste : fleurs, arbres, nourriture, encens, mer...),
"ambiance" (calme, festive, mélancolique, énergique...),
"odeurs_probables" (liste d'odeurs que ces éléments peuvent dégager)."""


def analyser_photo(chemin_photo: str) -> dict:
    reponse = ollama.chat(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": PROMPT, "images": [chemin_photo]}],
        format="json",
    )
    return json.loads(reponse["message"]["content"])


def construire_question(description: dict, recit: str = "") -> str:
    """Texte final envoyé au RAG (/ask) : récit du client + ce que montre la photo."""
    morceaux = []
    if recit:
        morceaux.append(f"Récit du client : {recit}")
    morceaux.append(
        "Ce que montre la photo : "
        f"lieu {description.get('lieu')}, culture {description.get('pays_ou_culture_visible')}, "
        f"moment {description.get('moment')}, météo {description.get('meteo')}, "
        f"éléments {', '.join(description.get('elements_visibles', []))}, "
        f"ambiance {description.get('ambiance')}, "
        f"odeurs probables {', '.join(description.get('odeurs_probables', []))}."
    )
    morceaux.append(
        "Propose un profil olfactif (tête, cœur, fond) avec des ingrédients du catalogue "
        "Givaudan présents dans la base, en citant les sources (S001...)."
    )
    return "\n".join(morceaux)


def envoyer_au_rag(question: str) -> dict:
    """Envoie la question à l'API (qui doit tourner : uvicorn api:app ...)."""
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8000/ask", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


if __name__ == "__main__":
    photo = sys.argv[1]
    recit = sys.argv[2] if len(sys.argv) > 2 else ""
    print("1/2 Analyse de la photo...")
    desc = analyser_photo(photo)
    print(json.dumps(desc, ensure_ascii=False, indent=2))
    question = construire_question(desc, recit)
    print("\n2/2 Envoi au RAG...")
    reponse = envoyer_au_rag(question)
    print(json.dumps(reponse, ensure_ascii=False, indent=2))
