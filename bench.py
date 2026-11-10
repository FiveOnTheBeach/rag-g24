"""Benchmark de plusieurs LLM Ollama sur le RAG du projet.

Pour chaque modèle, pose les mêmes questions (questions_test.csv) avec les
mêmes passages retrouvés dans ChromaDB, puis mesure :
  - le temps de réponse (secondes)
  - la vitesse de génération (tokens par seconde)
  - si le mot-clé attendu apparaît dans la réponse (score automatique)

Prérequis :
  - Ollama lancé, base remplie (python3 ingest.py)
  - les modèles téléchargés (ollama pull <modèle>) ; ceux qui manquent sont ignorés

Usage :
    python3 bench.py                         # tous les modèles de MODELS
    python3 bench.py qwen3.5:4b gemma4:e4b   # seulement ces modèles

Résultat : resultats_benchmark.csv (à ouvrir dans Excel), avec deux colonnes
à remplir à la main : "correct" (oui / partiel / non) et "invente" (oui / non).
"""

import csv
import sys
import time
import unicodedata
from pathlib import Path

import ollama

import config
import rag

# Modèles comparés : modifie cette liste selon ce que tu as téléchargé
MODELS = [
    "qwen2.5:1.5b",    # modèle de départ du projet (référence)
    "qwen3.5:4b",
    "ministral-3:3b",
    "qwen3.5:9b",
    "ministral-3:8b",
    "gemma4:e4b",
]

QUESTIONS_FILE = config.BASE_DIR / "questions_test.csv"
OUTPUT_FILE = config.BASE_DIR / "resultats_benchmark.csv"

SYSTEM_PROMPT = """Tu es un assistant qui répond à des questions à partir de documents.
Règles :
- Réponds UNIQUEMENT à partir des extraits fournis.
- Si la réponse ne se trouve pas dans les extraits, dis clairement que l'information n'est pas précisée.
- Réponds en français, en quelques phrases maximum."""


def sans_accents(texte: str) -> str:
    """Minuscules sans accents, pour comparer « Éclair » et « eclair »."""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def retrouver_passages(question: str) -> str:
    """Les mêmes passages pour tous les modèles : seul le LLM change."""
    collection = rag.get_collection()
    result = collection.query(
        query_embeddings=[rag.embed_query(question)],
        n_results=min(config.TOP_K, collection.count()),
    )
    return "\n\n---\n\n".join(
        f"[{meta['chapter']}]\n{doc}"
        for doc, meta in zip(result["documents"][0], result["metadatas"][0])
    )


def demander(client: ollama.Client, model: str, messages: list[dict]):
    """Appelle le modèle sans le mode « réflexion » (plus rapide et comparable)."""
    try:
        return client.chat(model=model, messages=messages, think=False,
                           options={"temperature": 0.2})
    except ollama.ResponseError as exc:
        if "think" in str(exc).lower():  # modèle sans mode réflexion
            return client.chat(model=model, messages=messages,
                               options={"temperature": 0.2})
        raise


def main() -> None:
    models = sys.argv[1:] or MODELS
    client = ollama.Client(host=config.OLLAMA_HOST)

    if rag.get_collection().count() == 0:
        sys.exit("La base est vide : lance d'abord `python3 ingest.py`.")

    with QUESTIONS_FILE.open(encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    # Les passages sont calculés une seule fois, puis réutilisés pour chaque modèle
    print(f"Recherche des passages pour {len(questions)} questions...")
    contextes = {q["question"]: retrouver_passages(q["question"]) for q in questions}

    lignes, resume = [], []
    for model in models:
        print(f"\n=== {model} ===")
        try:
            # Échauffement : charge le modèle en mémoire (ce temps n'est pas compté)
            debut = time.perf_counter()
            demander(client, model, [{"role": "user", "content": "Bonjour"}])
            chargement = time.perf_counter() - debut
        except ollama.ResponseError as exc:
            print(f"  Ignoré ({exc}). Télécharge-le avec : ollama pull {model}")
            continue
        print(f"  Chargé en {chargement:.1f} s")

        temps, vitesses, bons, notes = [], [], 0, 0
        for q in questions:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extraits :\n\n{contextes[q['question']]}"
                                            f"\n\nQuestion : {q['question']}"},
            ]
            debut = time.perf_counter()
            reponse = demander(client, model, messages)
            duree = time.perf_counter() - debut

            texte = reponse["message"]["content"].strip()
            nb_tokens = reponse.get("eval_count") or 0
            duree_gen = (reponse.get("eval_duration") or 0) / 1e9
            vitesse = nb_tokens / duree_gen if duree_gen else 0.0

            mot_cle = q.get("mot_cle", "").strip()
            if mot_cle:
                trouve = sans_accents(mot_cle) in sans_accents(texte)
                notes += 1
                bons += trouve
                auto = "oui" if trouve else "non"
            else:
                auto = "à vérifier"  # question piège : à juger à la main

            temps.append(duree)
            vitesses.append(vitesse)
            print(f"  [{auto:>10}] {duree:5.1f} s  {q['question']}")
            lignes.append({
                "modele": model,
                "type": q.get("type", ""),
                "question": q["question"],
                "reponse_attendue": q.get("reponse_attendue", ""),
                "reponse_modele": texte,
                "mot_cle_trouve": auto,
                "secondes": round(duree, 2),
                "tokens_par_s": round(vitesse, 1),
                "correct": "",
                "invente": "",
            })

        resume.append((model, bons, notes, sum(temps) / len(temps),
                       sum(vitesses) / len(vitesses), chargement))

    if not lignes:
        sys.exit("Aucun modèle testé : vérifie qu'Ollama tourne et que les modèles sont téléchargés.")

    with OUTPUT_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(lignes[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(lignes)

    print("\n=== Résumé ===")
    print(f"{'Modèle':<18} {'Mots-clés':>10} {'Temps moy.':>11} {'Tokens/s':>9} {'Chargement':>11}")
    for model, bons, notes, t, v, c in resume:
        print(f"{model:<18} {f'{bons}/{notes}':>10} {t:>9.1f} s {v:>9.1f} {c:>9.1f} s")
    print(f"\nDétail par question : {OUTPUT_FILE.name} (remplis les colonnes correct et invente)")


if __name__ == "__main__":
    main()
