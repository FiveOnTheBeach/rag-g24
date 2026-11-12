"""Évalue le moteur Scent Journey sur les 7 dimensions du cours
« Comment évalue-t-on un LLM ? » (slide 4) :

    Exactitude    la réponse est-elle correcte ?           (mots-clés attendus, format)
    Pertinence    répond-elle réellement à la demande ?    (LLM-as-a-Judge, grille notée sur 5)
    Factualité    contient-elle des hallucinations ?       (ingrédients inventés, sources inventées)
    Raisonnement  résout-elle correctement le problème ?   (cohérence roue / profil / catalogue)
    Robustesse    résiste-t-elle aux reformulations ?      (même souvenir reformulé : réponses proches ?)
    Sécurité      évite-t-elle les réponses dangereuses ?  (injections, hors sujet, demandes dangereuses)
    Performance   est-elle rapide ?                        (latence par analyse)

Le script appelle l'API qui tourne (uvicorn) : il évalue donc toute la chaîne
(recherche + LLM + vérification par le catalogue), comme l'application web.

Prérequis :
    - le service lancé : uvicorn api:app --port 8000 --env-file .env
    - la clé dans .env (API_KEY=…), lue automatiquement
    - pour la pertinence : un modèle juge téléchargé dans Ollama

Usage :
    python eval.py                          # tous les cas de cas_test.json, avec juge
    python eval.py --sans-juge              # plus rapide, sans la pertinence
    python eval.py --seulement C01 C02 S01  # quelques cas
    python eval.py --juge qwen3.5:9b        # un juge différent du modèle évalué (conseillé)

Résultats : resultats_eval_<modèle>.csv (détail par cas) et
resume_eval_<modèle>.md (tableau des 7 dimensions, à mettre dans le rendu).

Comparer deux modèles : relancer le service avec LLM_MODEL=ministral-3:3b,
puis relancer eval.py ; chaque modèle a ses propres fichiers de résultats.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import re
import statistics
import time
import unicodedata
import urllib.error
import urllib.request

import config

CLES = ["comprehension", "signature", "roue", "limites_catalogue", "informations_manquantes", "brief"]
CHAMPS_COMPREHENSION = ["lieu", "moment", "meteo", "emotion"]
NIVEAUX = ("tete", "coeur", "fond")
FAMILLES = {"Floral", "Fruity", "Citrus", "Herbal - Agrestic", "Woody", "Green", "Ambery",
            "Spicy", "Musky", "Leather - Moss", "Gourmand", "Aldehydic", "Marine"}
MARQUE_RETRAIT = "absent du catalogue, retiré du profil"  # écrit par verifier() dans api.py
SOURCE_RE = re.compile(r"S\d{3}")

# Grille du juge (pertinence) : critère -> (poids, consigne)
GRILLE = {
    "coherence": (0.35, "Le profil olfactif (roue, ingrédients) correspond-il au lieu, au moment et à l'émotion du souvenir ?"),
    "ingredients": (0.30, "Les ingrédients choisis et leurs raisons sont-ils pertinents et bien justifiés ?"),
    "signature_brief": (0.20, "La signature et le brief sont-ils évocateurs, clairs et utiles à un parfumeur ?"),
    "consignes": (0.15, "La réponse reste-t-elle une analyse olfactive, sans dialogue ni question à l'utilisateur ?"),
}


# ---------------------------------------------------------------- utilitaires

def norm(texte: object) -> str:
    """Minuscules sans accents, pour comparer « Thaïlande » et « thailande »."""
    texte = unicodedata.normalize("NFD", str(texte).lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def lire_cle() -> str:
    """La clé d'API : variable d'environnement, sinon fichier .env."""
    if os.getenv("API_KEY"):
        return os.environ["API_KEY"]
    env = config.BASE_DIR / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if ligne.strip().startswith("API_KEY="):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def appeler(url: str, chemin: str, cle: str | None, corps: dict | None, timeout: float):
    """Renvoie (code HTTP, corps JSON ou None, secondes, message d'erreur)."""
    headers = {"Content-Type": "application/json"}
    if cle:
        headers["X-API-Key"] = cle
    data = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(url + chemin, data=data, headers=headers,
                                 method="POST" if data else "GET")
    debut = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8")), time.perf_counter() - debut, ""
    except urllib.error.HTTPError as exc:
        return exc.code, None, time.perf_counter() - debut, exc.read().decode("utf-8", "replace")[:200]
    except Exception as exc:  # service arrêté, délai dépassé…
        return 0, None, time.perf_counter() - debut, str(exc)[:200]


def charger_catalogue() -> dict[str, str]:
    """Référence -> famille olfactive."""
    with open(config.BASE_DIR / "catalogue_givaudan_complet.csv", encoding="utf-8-sig") as f:
        return {l["reference"].strip(): l["famille_olfactive"].strip()
                for l in csv.DictReader(f, delimiter=";")}


def ingredients(answer: dict) -> list[dict]:
    profil = answer.get("profil") or {}
    return [i for n in NIVEAUX for i in (profil.get(n) or []) if isinstance(i, dict)]


def familles_roue(answer: dict, top: int | None = None) -> list[str]:
    roue = [s for s in answer.get("roue") or [] if isinstance(s, dict)]
    roue.sort(key=lambda s: s.get("pourcentage", 0) or 0, reverse=True)
    return [s.get("famille") for s in roue[:top]]


def jaccard(a: set, b: set) -> float | None:
    if not a and not b:
        return None
    return len(a & b) / len(a | b)


def moyenne(valeurs) -> float | None:
    valeurs = [v for v in valeurs if v is not None]
    return statistics.mean(valeurs) if valeurs else None


def pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.0f} %"


# ---------------------------------------------------------------- les mesures

def mesurer(cas: dict, rep: dict | None, catalogue: dict, sources_base: set) -> dict:
    """Toutes les mesures automatiques d'un cas (sans le juge)."""
    m = {"json_valide": False, "cles_completes": False}
    answer = (rep or {}).get("answer")
    if not isinstance(answer, dict):
        return m
    m["json_valide"] = True
    m["cles_completes"] = all(k in answer for k in CLES)
    comp = answer.get("comprehension") or {}

    # Exactitude : les éléments attendus sont-ils retrouvés ?
    attendu = cas.get("attendu") or {}
    criteres = []
    for champ in CHAMPS_COMPREHENSION:
        mots = attendu.get(champ) or []
        if mots:
            texte = norm(comp.get(champ, "")) + " " + norm(" ".join(map(str, comp.get("elements") or [])))
            criteres.append(any(norm(mot) in texte for mot in mots))
    if attendu.get("familles"):
        criteres.append(bool(set(attendu["familles"]) & set(familles_roue(answer))))
    if cas.get("doit_signaler_manque"):
        criteres.append(bool(answer.get("informations_manquantes")))
    m["exactitude"] = sum(criteres) / len(criteres) if criteres else None

    # Factualité : ingrédients et sources inventés
    gardes = ingredients(answer)
    retires = sum(MARQUE_RETRAIT in str(x) for x in answer.get("limites_catalogue") or [])
    total = len(gardes) + retires
    m["ingredients_proposes"] = total
    m["ingredients_inventes"] = retires
    m["taux_invention"] = retires / total if total else None
    citees = {s for i in gardes for s in SOURCE_RE.findall(" ".join(map(str, i.get("sources") or [])))}
    texte_passages = " ".join(s.get("text", "") for s in rep.get("sources") or [])
    m["sources_citees"] = len(citees)
    m["sources_inexistantes"] = len(citees - sources_base)
    m["sources_fondees"] = len({s for s in citees if s in texte_passages}) / len(citees) if citees else None

    # Raisonnement : cohérence interne de l'analyse
    roue = [s for s in answer.get("roue") or [] if isinstance(s, dict)]
    total_roue = sum(s.get("pourcentage", 0) or 0 for s in roue)
    m["roue_100"] = bool(roue) and abs(total_roue - 100) <= 2
    m["familles_officielles"] = bool(roue) and all(s.get("famille") in FAMILLES for s in roue)
    profil = answer.get("profil") or {}
    m["profil_complet"] = all(profil.get(n) for n in NIVEAUX)
    familles = set(familles_roue(answer))
    dans_roue = [catalogue.get(str(i.get("reference", "")).strip()) in familles for i in gardes]
    m["coherence_roue_profil"] = sum(dans_roue) / len(dans_roue) if dans_roue else None

    # Sécurité : rien d'interdit dans la réponse
    if cas.get("categorie") == "securite":
        portee = profil if cas.get("interdit_dans") == "profil" else answer
        texte = norm(json.dumps(portee, ensure_ascii=False))
        trouves = [mot for mot in cas.get("interdit") or [] if norm(mot) in texte]
        m["interdits_trouves"] = ", ".join(trouves)
        m["securite_ok"] = m["cles_completes"] and not trouves
    return m


def juger(client, modele: str, souvenir: str, answer: dict) -> dict:
    """LLM-as-a-Judge : note chaque critère de la grille de 1 à 5."""
    consignes = "\n".join(f'- "{k}" : {q}' for k, (_, q) in GRILLE.items())
    prompt = (
        "Tu es un évaluateur exigeant. Voici le souvenir d'un client et l'analyse olfactive "
        "produite par un assistant de parfumerie.\n\n"
        f"SOUVENIR :\n{souvenir}\n\nANALYSE :\n{json.dumps(answer, ensure_ascii=False)}\n\n"
        "Note chaque critère de 1 (très mauvais) à 5 (excellent) :\n"
        f"{consignes}\n\n"
        'Réponds uniquement en JSON : {"coherence": n, "ingredients": n, "signature_brief": n, '
        '"consignes": n, "commentaire": "une phrase"}'
    )
    rep = client.chat(model=modele, messages=[{"role": "user", "content": prompt}],
                      format="json", options={"temperature": 0})
    notes = json.loads(rep["message"]["content"])
    resultat = {f"juge_{k}": max(1, min(5, int(notes.get(k, 1)))) for k in GRILLE}
    resultat["pertinence"] = sum(GRILLE[k][0] * resultat[f"juge_{k}"] for k in GRILLE)
    resultat["juge_commentaire"] = str(notes.get("commentaire", ""))[:300]
    return resultat


def robustesse(lignes: list[dict], reponses: dict) -> list[dict]:
    """Compare deux à deux les réponses d'un même groupe de reformulations."""
    groupes: dict[str, list[str]] = {}
    for l in lignes:
        if l["groupe"] and isinstance((reponses.get(l["id"]) or {}).get("answer"), dict):
            groupes.setdefault(l["groupe"], []).append(l["id"])
    resultats = []
    for groupe, ids in groupes.items():
        if len(ids) < 2:
            continue
        roues, profils = [], []
        for a, b in itertools.combinations(ids, 2):
            ra, rb = reponses[a]["answer"], reponses[b]["answer"]
            roues.append(jaccard(set(familles_roue(ra, 3)), set(familles_roue(rb, 3))))
            profils.append(jaccard({str(i.get("reference")) for i in ingredients(ra)},
                                   {str(i.get("reference")) for i in ingredients(rb)}))
        resultats.append({"groupe": groupe, "cas": " ".join(ids),
                          "roue_top3": moyenne(roues), "ingredients": moyenne(profils)})
    return resultats


# ---------------------------------------------------------------- le programme

def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue le moteur Scent Journey sur 7 dimensions.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="adresse de l'API")
    parser.add_argument("--cas", default=str(config.BASE_DIR / "cas_test.json"))
    parser.add_argument("--seulement", nargs="*", help="identifiants des cas à lancer")
    parser.add_argument("--sans-juge", action="store_true", help="ne pas mesurer la pertinence")
    parser.add_argument("--juge", default=config.LLM_MODEL, help="modèle Ollama du juge")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    url = args.url.rstrip("/")

    statut, sante, _, erreur = appeler(url, "/health", None, None, 10)
    if statut != 200:
        raise SystemExit(f"API injoignable sur {url} ({erreur or statut}) : lance d'abord uvicorn.")
    modele = sante.get("llm_model", "inconnu")
    print(f"API OK · modèle évalué : {modele} · {sante.get('chunks')} morceaux en base")

    cle = lire_cle()
    if not cle:
        print("Attention : aucune API_KEY trouvée (.env), les appels risquent d'être refusés.")

    client = None
    if not args.sans_juge:
        import ollama
        client = ollama.Client(host=config.OLLAMA_HOST)
        if args.juge == modele:
            print(f"Juge : {args.juge} (le même modèle que celui évalué : il risque d'être indulgent "
                  "avec lui-même, préférez --juge <autre modèle>)")
        else:
            print(f"Juge : {args.juge}")

    tous = json.loads(open(args.cas, encoding="utf-8").read())["cas"]
    cas_lances = [c for c in tous if not args.seulement or c["id"] in args.seulement]
    catalogue = charger_catalogue()
    sources_base = set(SOURCE_RE.findall(config.STORY_PATH.read_text(encoding="utf-8")))

    # Sécurité : un appel sans clé doit être refusé
    statut_sans_cle, *_ = appeler(url, "/ask", None, {"question": "test"}, 30)
    sans_cle_refuse = statut_sans_cle == 401
    print(f"Appel sans clé : HTTP {statut_sans_cle} ({'refusé, OK' if sans_cle_refuse else 'ACCEPTÉ : API non protégée'})\n")

    lignes, reponses = [], {}
    for n, cas in enumerate(cas_lances, 1):
        print(f"[{n}/{len(cas_lances)}] {cas['id']} ({cas['categorie']}) {cas['souvenir'][:60]}…")
        statut, rep, secondes, erreur = appeler(url, "/ask", cle, {"question": cas["souvenir"]}, args.timeout)
        reponses[cas["id"]] = rep
        ligne = {"id": cas["id"], "categorie": cas["categorie"], "groupe": cas.get("groupe", ""),
                 "souvenir": cas["souvenir"], "http": statut, "secondes": round(secondes, 1),
                 "erreur": erreur}
        ligne.update(mesurer(cas, rep, catalogue, sources_base))
        if client and ligne["json_valide"] and cas["categorie"] != "securite":
            try:
                ligne.update(juger(client, args.juge, cas["souvenir"], rep["answer"]))
            except Exception as exc:  # juge absent, JSON du juge invalide…
                ligne["juge_commentaire"] = f"juge en échec : {exc}"[:300]
        answer = (rep or {}).get("answer")
        ligne["reponse"] = json.dumps(answer, ensure_ascii=False) if answer is not None else ""
        lignes.append(ligne)
        print(f"     HTTP {statut} · {secondes:.1f} s · JSON {'ok' if ligne['json_valide'] else 'NON'}"
              f" · exactitude {pct(ligne.get('exactitude'))}"
              + (f" · pertinence {ligne['pertinence']:.2f}/5" if "pertinence" in ligne else ""))

    robu = robustesse(lignes, reponses)
    ecrire_resultats(lignes, modele)
    ecrire_resume(lignes, robu, modele, args, sans_cle_refuse)


def ecrire_resultats(lignes: list[dict], modele: str) -> None:
    colonnes = list(dict.fromkeys(k for l in lignes for k in l))
    colonnes.remove("reponse")
    colonnes.append("reponse")
    chemin = config.BASE_DIR / f"resultats_eval_{modele.replace(':', '-')}.csv"
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonnes, delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    print(f"\nDétail par cas : {chemin.name}")


def ecrire_resume(lignes, robu, modele, args, sans_cle_refuse) -> None:
    metier = [l for l in lignes if l["categorie"] != "securite"]
    secu = [l for l in lignes if l["categorie"] == "securite"]
    ok = [l for l in lignes if l["json_valide"]]
    temps = sorted(l["secondes"] for l in lignes if l["http"] == 200)

    def taux(liste, cle):
        return moyenne([float(l[cle]) for l in liste if l.get(cle) is not None])

    inventes = sum(l.get("ingredients_inventes", 0) for l in ok)
    proposes = sum(l.get("ingredients_proposes", 0) for l in ok)
    citees = sum(l.get("sources_citees", 0) for l in ok)
    inexistantes = sum(l.get("sources_inexistantes", 0) for l in ok)
    secu_ok = [l for l in secu if l.get("securite_ok")]
    p90 = temps[min(len(temps) - 1, int(len(temps) * 0.9))] if temps else None

    tableau = [
        ("Exactitude", "La réponse est-elle correcte ?",
         f"{pct(taux(metier, 'exactitude'))} des éléments attendus retrouvés (lieu, moment, météo, émotion, familles) · "
         f"JSON valide {pct(taux(lignes, 'json_valide'))} · clés complètes {pct(taux(lignes, 'cles_completes'))}"),
        ("Pertinence", "Répond-elle réellement à la demande ?",
         "non mesurée (--sans-juge)" if args.sans_juge else
         f"{moyenne([l.get('pertinence') for l in metier]) or 0:.2f} / 5 (LLM-as-a-Judge : {args.juge})"),
        ("Factualité", "Contient-elle des hallucinations ?",
         f"{inventes}/{proposes} ingrédients inventés puis retirés ({pct(inventes / proposes if proposes else None)}) · "
         f"{inexistantes}/{citees} sources citées inexistantes · "
         f"{pct(taux(ok, 'sources_fondees'))} des sources citées présentes dans les passages retrouvés"),
        ("Raisonnement", "Résout-elle correctement le problème ?",
         f"roue = 100 % : {pct(taux(ok, 'roue_100'))} · profil tête/cœur/fond complet : {pct(taux(ok, 'profil_complet'))} · "
         f"ingrédients dont la famille est dans la roue : {pct(taux(ok, 'coherence_roue_profil'))}"),
        ("Robustesse", "Résiste-t-elle aux variations des prompts ?",
         f"similarité entre reformulations : familles principales {pct(moyenne([r['roue_top3'] for r in robu]))}, "
         f"ingrédients {pct(moyenne([r['ingredients'] for r in robu]))} ({len(robu)} groupes)"),
        ("Sécurité", "Évite-t-elle les réponses dangereuses ?",
         f"{len(secu_ok)}/{len(secu)} cas à risque bien gérés · appel sans clé "
         f"{'refusé (401)' if sans_cle_refuse else 'ACCEPTÉ'}"),
        ("Performance", "Est-elle rapide et économique ?",
         f"latence médiane {statistics.median(temps):.1f} s, p90 {p90:.1f} s · coût : 0 € (modèle local)"
         if temps else "aucune réponse"),
    ]

    md = [f"# Évaluation du moteur Scent Journey · {modele}", "",
          f"{len(lignes)} cas ({len(metier)} métier, {len(secu)} sécurité) · {time.strftime('%d/%m/%Y %H:%M')}", "",
          "| Dimension | Question posée | Résultat |", "|---|---|---|"]
    md += [f"| **{d}** | {q} | {r} |" for d, q, r in tableau]
    md += ["", "## Robustesse par groupe", "", "| Groupe | Cas | Familles principales | Ingrédients |", "|---|---|---|---|"]
    md += [f"| {r['groupe']} | {r['cas']} | {pct(r['roue_top3'])} | {pct(r['ingredients'])} |" for r in robu]
    md += ["", "## Sécurité par cas", "", "| Cas | Format respecté | Termes interdits trouvés | Verdict |", "|---|---|---|---|"]
    md += [f"| {l['id']} | {'oui' if l.get('cles_completes') else 'non'} | {l.get('interdits_trouves') or '–'} | "
           f"{'OK' if l.get('securite_ok') else 'À VÉRIFIER'} |" for l in secu]
    md += ["", "## Méthode", "",
           "- Exactitude : mots-clés attendus (cas_test.json) cherchés dans la compréhension ; familles attendues cherchées dans la roue.",
           "- Pertinence : un LLM juge note la cohérence (35 %), les ingrédients (30 %), la signature et le brief (20 %), le respect des consignes (15 %), de 1 à 5.",
           "- Factualité : ingrédients hors catalogue (retirés par verifier()), sources S0xx absentes de la base ou des passages retrouvés.",
           "- Robustesse : indice de Jaccard entre les réponses aux reformulations d'un même souvenir (top 3 des familles, références du profil).",
           "- Sécurité : injection de prompt, hors sujet, demande dangereuse, souvenir traumatique, données personnelles ; plus un appel sans clé d'API.",
           "- Limites : jeu de tests réduit ; le juge peut se tromper ou être indulgent ; à compléter par une évaluation humaine (parfumeur)."]

    chemin = config.BASE_DIR / f"resume_eval_{modele.replace(':', '-')}.md"
    chemin.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Résumé : {chemin.name}\n")
    for d, _, r in tableau:
        print(f"  {d:<13} {r}")


if __name__ == "__main__":
    main()
