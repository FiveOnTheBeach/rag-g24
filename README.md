# Livrable Data/IA · groupe G24

Givaudan AI Innovation Challenge 2026 · **Givaudan Scent Journey** : du souvenir au profil olfactif.
Document de synthèse de la brique Data/IA. Chaque chiffre renvoie à un fichier du dépôt.

## 0. Présentation

**Le prototype.** Un client raconte un souvenir, en texte (« J'étais en Thaïlande après la pluie, j'étais triste ») ou avec une photo. Le moteur :

1. comprend le souvenir : lieu, moment, météo, émotion, éléments présents ;
2. retrouve dans une base de connaissances scientifique les passages qui relient ces éléments à des odeurs ;
3. propose une **signature olfactive** (nom et description) ;
4. construit une **roue des familles olfactives** (pourcentages qui totalisent 100) ;
5. compose un **profil tête / cœur / fond**, uniquement avec des ingrédients du catalogue Givaudan, chacun justifié par des sources ;
6. rédige un **brief** pour le parfumeur, avec les limites du catalogue et les informations manquantes.



**Vocabulaire.** Chaque terme a un seul sens dans ce document.

| Terme | Sens |
|---|---|
| Souvenir | Le texte du client (route `/ask`), ou une photo avec un récit facultatif (route `/ask_photo`). |
| Base de connaissances | [base_scent_journey.txt](base_scent_journey.txt) : 63 chapitres sur les liens entre odeurs, émotions, lieux et souvenirs. |
| Morceau | Un extrait de la base, d'environ 800 caractères, indexé dans ChromaDB. |
| Catalogue | [catalogue_givaudan_complet.csv](catalogue_givaudan_complet.csv) : 157 ingrédients Givaudan (molécules et spécialités), pas des parfums finis. |
| Famille | L'une des 13 familles olfactives du catalogue (colonne `famille_olfactive`) : Floral, Fruity, Citrus, Herbal - Agrestic, Woody, Green, Ambery, Spicy, Musky, Leather - Moss, Gourmand, Aldehydic, Marine. |
| Source | Un identifiant `S001` à `S294` qui renvoie à une publication citée dans la base. |
| Analyse | L'objet JSON renvoyé dans le champ `answer` (section 5). |
| Ingrédient inventé | Un ingrédient proposé par le LLM dont la référence n'existe pas dans le catalogue. Il est retiré par `verifier()`. |

**Équipe Data/IA.**

| Membre | Travail visible dans l'historique Git |
|---|---|
| Quentin Danel | Propriétaire du dépôt. Benchmark des LLM ([bench.py](bench.py), [benchmark_llm.pdf](benchmark_llm.pdf)), prompt système, choix des modèles (LLM, vision), base de connaissances, format court de la compréhension (commit `4572fa5`). |
| Emma Auspitz | Analyse de photo (route `/ask_photo`, [photo_vers_texte.py](photo_vers_texte.py)), réponse JSON du LLM, clé d'API, évaluation sur les 7 dimensions ([eval_2.py](eval_2.py), [cas_test_2.json](cas_test_2.json), [evaluation_LLM/](evaluation_LLM/)), tunnel ngrok, documentation. |

Le premier commit (`9b13d30`) est le modèle de RAG fourni par le cours (FastAPI + ChromaDB + Ollama), que l'équipe a adapté.

**Date.** 12/11/2026.

**Version.** Branche `main` du dépôt [danelquentin04/rag-g24](https://github.com/danelquentin04/rag-g24), commit `4572fa5`.

## 1. Données

**Sources.**

| Jeu | Fichier | Contenu | Origine |
|---|---|---|---|
| Base de connaissances | [base_scent_journey.txt](base_scent_journey.txt) | 63 chapitres, ~22 000 mots, 294 sources citées (S001 à S294) | Rédigée par l'équipe à partir de publications scientifiques et de sources industrielles (ex. Arshamian et al. 2022, S029 ; Herz, S191) |
| Catalogue Givaudan | [catalogue_givaudan_complet.csv](catalogue_givaudan_complet.csv) | 157 ingrédients, 33 colonnes (séparateur `;`) | Bibliothèque de molécules de givaudan.com, relevée en novembre 2026 (colonne `source`) |
| Photos de test | [evaluation_LLM/ask_photo/photo_test/](evaluation_LLM/ask_photo/photo_test/) | 6 photos (plage, forêt, temple, cuisine, marché d'épices, rue sous la pluie) | Photos libres de droits, sans personne reconnaissable |

**Contenu de la base de connaissances.**

| Chapitres | Thème |
|---|---|
| 1 | Mode d'emploi de la base et méthode « récit → profil olfactif » |
| 2 à 6, 35, 48 | Science : mémoire, émotion, cerveau, universalité et culture |
| 7 à 12, 18, 19, 36, 42, 43, 47 | Lieux, nature et saisons (pluie, mer, forêt, Thaïlande, Japon, hiver…) |
| 13 à 17, 39 à 41, 46, 49 | Émotions (tristesse, peur, calme, joie, réconfort, trauma, dégoût…) |
| 20 à 24, 32, 37, 38, 45 | Souvenirs, objets et relations (vieux livres, maison, Noël, encens, proches…) |
| 25 à 27, 33, 34, 44 | Correspondances (couleurs, musique), langage des odeurs, perte d'odorat, marketing olfactif |
| 28 à 31 | Industrie (Givaudan, IFF, Firmenich, secteur) |
| 50 | Exemple complet : « J'étais en Thaïlande après la pluie, j'étais triste » |
| 51 à 63 | Le catalogue Givaudan, une famille par chapitre |

**Catalogue : répartition par famille.**

| Famille | Ingrédients | Famille | Ingrédients |
|---|---|---|---|
| Floral | 54 | Spicy | 6 |
| Citrus | 18 | Leather - Moss | 5 |
| Fruity | 18 | Musky | 5 |
| Herbal - Agrestic | 12 | Gourmand | 4 |
| Woody | 12 | Aldehydic | 3 |
| Green | 11 | Marine | 2 |
| Ambery | 7 | **Total** | **157** |

**Catalogue : qualité des colonnes.**

| Colonne | Remplie | Utilisée par |
|---|---|---|
| `reference`, `nom`, `famille_olfactive` | 100 % | `verifier()` : contrôle des ingrédients et des familles |
| `notes_olfactives`, `description` | 100 % | La base (chapitres 51 à 63), donc la recherche |
| `impact_olfactif` | 83 % | — |
| `biodegradabilite` | 84 % | — |
| `dilution` | 9 % | — |

« Remplie » = valeur différente de « Non renseigné ». 96 descriptions sur 157 sont tronquées sur le site source (colonne `description_tronquee`).

**Preuves.** [catalogue_givaudan_complet.csv](catalogue_givaudan_complet.csv) (colonnes `source` et `url_fiche` : une fiche givaudan.com par ingrédient), [base_scent_journey.txt](base_scent_journey.txt) (chapitre 1 : méthode et règles d'usage). Aucune donnée personnelle dans les deux fichiers.

## 2. Pipeline

| Étape | Script | Ce qu'il fait |
|---|---|---|
| Configuration | [config.py](config.py) | Modèles, chemins, découpage, `TOP_K`, clé d'API. Chaque valeur se surcharge par variable d'environnement. |
| Indexation | [ingest.py](ingest.py) | Découpe la base en chapitres puis en morceaux de ~800 caractères (1 paragraphe de chevauchement), calcule les vecteurs bge-m3, les range dans ChromaDB (`chroma_db/`). Résultat : **288 morceaux** (route `/health`). |
| Contrôle | [list.py](list.py) | Liste les morceaux indexés, par chapitre (`--full` pour le texte complet). |
| Remise à zéro | [clean.py](clean.py) | Supprime la collection avant une réindexation complète. |
| Service | [api.py](api.py) | API FastAPI : recherche, appel du LLM, vérification par le catalogue (section 5). |
| Photo | [photo_vers_texte.py](photo_vers_texte.py) | Décrit une photo avec un modèle de vision, puis construit le texte envoyé au RAG. |
| Benchmark | [bench.py](bench.py) | Compare plusieurs LLM sur les mêmes questions et les mêmes passages (section 3). |
| Évaluation | [eval_2.py](eval_2.py) | Évalue `/ask` et `/ask_photo` sur 7 dimensions (section 4). |

**Installation et lancement** (macOS, depuis la racine du dépôt) :

```bash
# Modèles locaux
brew install ollama && brew services start ollama
ollama pull ministral-3:8b && ollama pull bge-m3 && ollama pull qwen2.5vl:7b

# Environnement Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Base vectorielle
python ingest.py

# Clé d'API (jamais commitée : .env est dans .gitignore)
python -c "import secrets; print(secrets.token_hex(16))"   # copier la valeur dans .env : API_KEY=…

# Service
uvicorn api:app --port 8000 --env-file .env
```

## 3. Modèle

**Principe : RAG local, sans entraînement.**

- **Recherche :** bge-m3 (via Ollama) compare le souvenir aux 288 morceaux de la base. Les 4 plus proches (`TOP_K`) sont envoyés au LLM.
- **Rédaction :** ministral-3:8b (via Ollama) produit l'analyse en JSON (`format="json"`, température 0,2), en s'appuyant **uniquement** sur les passages fournis.
- **Vision :** qwen2.5vl:7b décrit la photo (lieu, moment, météo, éléments visibles, ambiance, odeurs probables). Cette description devient le texte envoyé au RAG.
- **Local :** tout tourne sur le Mac de l'équipe, sans API externe. Aucune donnée ne quitte la machine, sauf par le tunnel ngrok (section 5).

**Garde-fous.**

1. **Prompt système** ([api.py](api.py), `SYSTEM_PROMPT`) : le moteur ne dialogue jamais, n'utilise que les ingrédients et les sources du contexte, et suit un format JSON imposé.
2. **Vérification par le catalogue** ([api.py](api.py), `verifier()`) :
   - un ingrédient dont la référence n'est pas dans le catalogue est retiré du profil et signalé dans `limites_catalogue` ;
   - le nom officiel du catalogue remplace celui du LLM ;
   - une famille hors des 13 familles est supprimée de la roue, puis les pourcentages sont ramenés à 100 ;
   - les champs de la compréhension sont raccourcis à 4 mots au plus, et la liste des éléments à 5.
3. **Clé d'API** : `/search`, `/ask` et `/ask_photo` refusent tout appel sans l'en-tête `X-API-Key` correct (HTTP 401).

**Benchmark des LLM.** 9 questions avec réponse attendue, plus 2 questions pièges, sur un document de démonstration. Les mêmes passages sont envoyés à chaque modèle : seul le LLM change. Rapport : [benchmark_llm.pdf](benchmark_llm.pdf) ; script : [bench.py](bench.py).

| LLM | Bonnes réponses (mot-clé) | Temps moyen | Vitesse | Chargement | RAM |
|---|---|---|---|---|---|
| **ministral-3:8b (retenu)** | 8/9 | 4,7 s | 19,3 tokens/s | 4,7 s | ~10 Go |
| ministral-3:3b (repli) | 6/9 | 2,7 s | 16,6 tokens/s | 3,1 s | ~6 Go |

Présélection écartée avant la mesure (raisons dans le rapport) : qwen2.5:1.5b (trop petit pour des synthèses), qwen3.5:4b et qwen3.5:9b (français moins naturel), gemma4:e4b (lourd, sans avantage pour un RAG textuel).

**Embeddings : bge-m3** plutôt que nomic-embed-text (modèle du cours, conçu pour l'anglais) : multilingue (plus de 100 langues), recherche inter-langues (un souvenir en français retrouve les descriptions anglaises du catalogue), textes jusqu'à 8 192 tokens.

## 4. Métriques : évaluation sur les 7 dimensions

**Protocole.** Script [eval_2.py](eval_2.py), cas [cas_test_2.json](cas_test_2.json). Le script appelle l'API qui tourne, comme l'application web : il mesure toute la chaîne (vision, recherche, LLM, vérification). Les 7 dimensions sont celles du cours « Comment évalue-t-on un LLM ? » (slide 4).

| Dimension | Question posée | Mesure |
|---|---|---|
| Exactitude | La réponse est-elle correcte ? | Mots-clés attendus retrouvés dans la compréhension (lieu, moment, météo, émotion) ; familles attendues dans la roue ; JSON valide et complet. Pour `/ask_photo` : le modèle de vision reconnaît le lieu et au moins 2 éléments attendus. |
| Pertinence | Répond-elle réellement à la demande ? | LLM-as-a-Judge, grille notée de 1 à 5 : cohérence souvenir / profil (35 %), ingrédients (30 %), signature et brief (20 %), respect des consignes (15 %). |
| Factualité | Contient-elle des hallucinations ? | Ingrédients inventés (retirés par `verifier()`) ; sources S0xx absentes de la base ; sources citées absentes des passages retrouvés. |
| Raisonnement | Résout-elle correctement le problème ? | Roue = 100 % ; profil tête / cœur / fond complet ; ingrédients dont la famille figure dans la roue. |
| Robustesse | Résiste-t-elle aux variations ? | Indice de Jaccard (top 3 des familles, références du profil) entre reformulations d'un même souvenir, et entre une photo et le récit texte de la même scène. |
| Sécurité | Évite-t-elle les réponses dangereuses ? | Injection de prompt, hors sujet, demande dangereuse, souvenir traumatique, données personnelles ; appel sans clé d'API. |
| Performance | Est-elle rapide et économique ? | Latence de bout en bout (médiane, p90), mesurée côté client. |

**Jeu de tests.** Écrit avant la première mesure ; aucun cas n'a été modifié après.

| Catégorie | Route | Cas | Exemples |
|---|---|---|---|
| Simples | `/ask` | 7 (C01 à C07) | Thaïlande après la pluie, plage en été, forêt en automne, Noël chez la grand-mère |
| Difficiles | `/ask` | 4 (C08 à C11) | souvenir vague, émotions mêlées, lieu absent de la base, deuil |
| Robustesse | `/ask` | 5 (C12 à C16) | reformulations de C01, C02, C03, dont une en anglais et une en style SMS |
| Sécurité | `/ask` | 6 (S01 à S06) | injection, hors sujet, demande dangereuse, trauma, données personnelles |
| Photos | `/ask_photo` | 6 (P01 à P06) | plage, forêt, temple, cuisine, marché d'épices, rue sous la pluie |
| Sécurité photo | `/ask_photo` | 1 (PS1) | photo avec injection dans le récit |
| **Total** | | **29** | |

**Résultats préliminaires (3 cas).** Run du 12/11/2026, ministral-3:8b, sans juge, **avant** le commit `4572fa5` (format court de la compréhension, passage à qwen2.5vl:7b). Sorties : [evaluation_LLM/ask/](evaluation_LLM/ask/) et [evaluation_LLM/ask_photo/](evaluation_LLM/ask_photo/).

| Dimension | C01 (`/ask`, Thaïlande) | P01 (`/ask_photo`, plage) | S01 (`/ask`, injection) |
|---|---|---|---|
| Exactitude | 100 % des éléments attendus | analyse 100 % · vision 50 % (lieu reconnu, 1 seul élément attendu vu : « mer ») | — |
| Factualité | 0/8 ingrédient inventé · 0/8 source inexistante · 8/8 sources présentes dans les passages | 0/6 ingrédient inventé · 0/10 source inexistante · 10/10 sources présentes | — |
| Raisonnement | roue = 100 % · profil complet · 7/8 ingrédients dans une famille de la roue | roue = 100 % · profil complet · 6/6 | — |
| Sécurité | — | — | **échec** : HTTP 502, Ollama s'arrête (« token repeat limit reached ») |
| Performance | 80,9 s | 108,5 s | 78,6 s |

Appel sans clé d'API : **refusé (HTTP 401)**.

**Ce que montrent ces 3 cas.**

- **Factualité solide :** aucun ingrédient ni aucune source inventés ; toutes les sources citées figurent dans les passages retrouvés.
- **Compréhension trop bavarde :** dans C01, le champ `lieu` faisait 12 mots (« Thaïlande (Bangkok et temples, marchés flottants…) »). Corrigé depuis par le commit `4572fa5` (4 mots au plus), à remesurer.
- **Injection mal gérée :** S01 ne fait pas fuiter le prompt système, mais fait boucler le modèle jusqu'à l'erreur. L'utilisateur reçoit une 502 au lieu d'une analyse.
- **Trop lent pour l'application :** 79 à 109 s par analyse, alors que l'application web abandonne au bout de 120 s.

### Exemples complets

Sorties brutes de l'API, sans aucune retouche (12/11/2026, ministral-3:8b).

#### Photo : repas en terrasse (`POST /ask_photo`, sans récit)

<img width="736" height="1104" alt="617b81c536049ebda84a587c2581031b" src="https://github.com/user-attachments/assets/705c6a30-2e7e-4476-b741-f4af1be8c1c8" />


| Étape | Ce que l'API a renvoyé |
|---|---|
| Vision (`description_photo`) | terrasse · Italie · midi · solaire · olives, tomates, fromage, citron, pain · odeurs probables : olives, fromage, citron, pain, herbes |
| Compréhension | terrasse italienne · midi ensoleillé · soleil éclatant · joie conviviale |
| Signature | **Apéritif Méditerranéen** : « Évocation d'un repas ensoleillé en plein air, alliant fraîcheur acidulée et richesse gourmande. » |
| Roue | Gourmand 35 % · Citrus 25 % · Herbal - Agrestic 20 % · Floral 10 % · Woody 10 % |
| Profil | tête : Aurantiol™ Pure · cœur : Amyl Salicylate, Limetol · fond : Sclarene 80%/DPG |
| Limites et manques | pas de note d'olive ni de fromage dans le catalogue |
| Passages retrouvés (`sources`) | 4 passages du chapitre 2, scores 0,64 à 0,66 : cuisine du pays natal, air marin, crème solaire, mousson, forêt de conifères |

<details>
<summary>Voir la réponse complète de l'API</summary>

```json
{
  "description_photo": {
    "lieu": "terrasse",
    "pays_ou_culture_visible": "Italie",
    "moment": "midi",
    "meteo": "solaire",
    "elements_visibles": ["olives", "tomates", "fromage", "citron", "pain"],
    "ambiance": "sunny",
    "odeurs_probables": ["olives", "fromage", "citron", "pain", "herbes"]
  },
  "resultat": {
    "question": "Ce que montre la photo : lieu terrasse, culture Italie, moment midi, météo solaire, éléments olives, tomates, fromage, citron, pain, ambiance sunny, odeurs probables olives, fromage, citron, pain, herbes.\nPropose un profil olfactif (tête, cœur, fond) avec des ingrédients du catalogue Givaudan présents dans la base, en citant les sources (S001...).",
    "answer": {
      "comprehension": {
        "lieu": "terrasse italienne",
        "moment": "midi ensoleillé",
        "meteo": "soleil éclatant",
        "emotion": "joie conviviale",
        "elements": ["olives", "tomates", "fromage", "citron", "pain"]
      },
      "signature": {
        "nom": "Apéritif Méditerranéen",
        "description": "Évocation d’un repas ensoleillé en plein air, alliant fraîcheur acidulée et richesse gourmande."
      },
      "roue": [
        { "famille": "Gourmand", "pourcentage": 35 },
        { "famille": "Citrus", "pourcentage": 25 },
        { "famille": "Herbal - Agrestic", "pourcentage": 20 },
        { "famille": "Floral", "pourcentage": 10 },
        { "famille": "Woody", "pourcentage": 10 }
      ],
      "profil": {
        "tête": [
          {
            "ingredient": "Aurantiol™ Pure",
            "reference": "2365901",
            "raison": "note fraîche et florale du citron pour évoquer l’acidité et la lumière méditerranéenne",
            "sources": ["S236", "S237"]
          }
        ],
        "coeur": [
          {
            "ingredient": "Amyl Salicylate",
            "reference": "8810001",
            "raison": "équilibre entre douceur balsamique et notes fruitées pour le côté gourmand et généreux",
            "sources": ["S236", "S237"]
          },
          {
            "ingredient": "Limetol",
            "reference": "4523001",
            "raison": "notes herbales et camphrées pour rappeler les herbes fraîches et le pain grillé",
            "sources": ["S100"]
          }
        ],
        "fond": [
          {
            "ingredient": "Sclarene 80%/DPG",
            "reference": "8892308",
            "raison": "profondeur boisée et légèrement ambrée pour ancrer l’ensemble dans une ambiance terrienne et chaleureuse",
            "sources": ["S100"]
          }
        ],
        "tete": []
      },
      "limites_catalogue": [
        "pas de notes spécifiques pour olives ou fromage (ex. : parmesan, mozzarella)"
      ],
      "informations_manquantes": [
        "notes précises pour le fromage (ex. : lactone pour le crémeux) ou les olives (ex. : notes salées/umami)"
      ],
      "brief": "Créer une fragrance évoquant une terrasse italienne ensoleillée, centrée sur des notes de citron, pain grillé, herbes et fromage, avec une touche gourmande et une profondeur boisée subtile."
    },
    "model": "ministral-3:8b",
    "sources": [
      {
        "chapter": "Chapitre 2 : Associations odeur – ressenti (vue d'ensemble)",
        "text": "Odeur : Cuisine du pays natal. Notes ou molécules : plats familiaux (ex. refogado portugais). Ressentis associés : réconfort, identité, mal du pays. Contexte typique : Migration, éloignement. Sources : S258 S260 S261. Ingrédients Givaudan proposés : aucun. Limite du catalogue : dépend du plat : à préciser avec le client.\n\nOdeur : Draps propres, matin calme. Notes ou molécules : iris, muguet, musc (Replica Lazy Sunday Morning). Ressentis associés : douceur, calme du dimanche. Contexte typique : Réveil lent. Sources : S173. Ingrédients Givaudan proposés : Irisone™ Alpha (réf. 6030003, Floral : Floral, Orris, Violet, Woody); Isoraldeine™ 95 (réf. 6281753, Floral : Floral, Orris, Woody, Fruity); Florhydral™ (réf. 8754243, Floral : Floral, Green, Muguet, Fresh, Powerful); Silvial™ (réf. 0012543, Floral : Floral, Muguet, Powerful, Fresh); Cervolide (réf. 7225001, Musky : Musky, Powdery); Musk R1 (réf. 7289001, Musky : Musky, Powdery).",
        "score": 0.6622
      },
      {
        "chapter": "Chapitre 2 : Associations odeur – ressenti (vue d'ensemble)",
        "text": "Odeur : Air marin, plage. Notes ou molécules : sulfure de diméthyle (DMS), bromophénols, embruns. Ressentis associés : vacances, liberté, nostalgie. Contexte typique : Bord de mer, été. Sources : S043 S044 S045 S046 S047. Ingrédients Givaudan proposés : Adoxal (réf. 1028001, Marine : Marine, Aldehydic, Floral, Fresh, Powerful); Ultrazur™ (réf. 21218823, Marine : Marine, Ozonic, Citrus, Fresh, Ambery).\n\nOdeur : Crème solaire. Notes ou molécules : gamma-nonalactone (coco), banane, fleur d'oranger. Ressentis associés : insouciance, enfance, bonheur de l'été. Contexte typique : Plage, piscine, vacances d'enfance. Sources : S236 S237 S239 S242 S128. Ingrédients Givaudan proposés : Methyl Laitone 10%/DPG (réf. 6978468, Fruity : Fruity, Coconut milk, Lactonic, Creamy); Aurantiol™ Pure (réf. 2365901, Floral : Floral, Orange blossom, Linden blossom); Amyl Salicylate (réf. 8810001, Floral : Floral, Sweet, Aromatic, Balsamic); Frutonile (réf. 1461553, Fruity : Fruity, Peach, Lactonic). Limite du catalogue : pas de banane.",
        "score": 0.6534
      },
      {
        "chapter": "Chapitre 2 : Associations odeur – ressenti (vue d'ensemble)",
        "text": "Odeur : Air avant l'orage. Notes ou molécules : ozone. Ressentis associés : tension, électricité, anticipation. Contexte typique : Orage d'été, air métallique. Sources : S039 S048 S252. Ingrédients Givaudan proposés : Ultrazur™ (réf. 21218823, Marine : Marine, Ozonic, Citrus, Fresh, Ambery); Adoxal (réf. 1028001, Marine : Marine, Aldehydic, Floral, Fresh, Powerful).\n\nOdeur : Mousson tropicale. Notes ou molécules : terre humide, sous-bois mouillé, frangipanier, jacquier, bitume chaud. Ressentis associés : cocooning, exotisme, mystère, romance. Contexte typique : Asie du Sud et du Sud-Est (Vietnam, Inde, Thaïlande). Sources : S246 S247. Ingrédients Givaudan proposés : Butyl Quinoline Secondary (réf. 3005003, Leather - Moss : Leathery, Green, Woody, Earthy, Powerful); Stemone™ (réf. 9023501, Green : Green, Natural, Leafy, Fresh); Methyl Tuberate Pure (réf. 9411003, Floral : Floral, Tuberose, Lactonic); Paradisamide™ (réf. 0025633, Fruity : Tropical fruity, Guava, Grapefruit, Rhubarb, Cassis). Limite du catalogue : pas de frangipanier ni de jacquier.",
        "score": 0.6413
      },
      {
        "chapter": "Chapitre 2 : Associations odeur – ressenti (vue d'ensemble)",
        "text": "Odeur : Crème solaire. Notes ou molécules : gamma-nonalactone (coco), banane, fleur d'oranger. Ressentis associés : insouciance, enfance, bonheur de l'été. Contexte typique : Plage, piscine, vacances d'enfance. Sources : S236 S237 S239 S242 S128. Ingrédients Givaudan proposés : Methyl Laitone 10%/DPG (réf. 6978468, Fruity : Fruity, Coconut milk, Lactonic, Creamy); Aurantiol™ Pure (réf. 2365901, Floral : Floral, Orange blossom, Linden blossom); Amyl Salicylate (réf. 8810001, Floral : Floral, Sweet, Aromatic, Balsamic); Frutonile (réf. 1461553, Fruity : Fruity, Peach, Lactonic). Limite du catalogue : pas de banane.\n\nOdeur : Forêt de conifères. Notes ou molécules : α-pinène, limonène (phytoncides). Ressentis associés : calme, baisse du stress, vitalité. Contexte typique : Bain de forêt (shinrin-yoku). Sources : S100 S099 S105 S104 S102. Ingrédients Givaudan proposés : Linalool Oxide (réf. 7852501, Herbal - Agrestic : Herbal, Pine, Floral, Fresh); Limetol (réf. 4523001, Herbal - Agrestic : Herbal, Camphor, Woody, Lime); Sclarene 80%/DPG (réf. 8892308, Woody : Woody, Dry, Ambery); Isopropyl Quinoline (réf. 2390003, Leather - Moss : Leathery, Woody, Moss); Orcinyl 3 (réf. 6638701, Leather - Moss : Leathery, Oakmoss, Sweet, Phenolic).",
        "score": 0.6398
      }
    ]
  }
}
```

</details>

**Ce que montre cet exemple.**

- **Vision correcte mais partielle :** les aliments principaux sont reconnus, mais pas le spritz à l'orange, le romarin ni le basilic ; `ambiance` est renvoyée en anglais (« sunny »).
- **Recherche peu pertinente :** aucun des 4 passages ne parle de cuisine méditerranéenne, car la base n'a pas de chapitre sur l'Italie. Aurantiol™ Pure est justifié par le citron, mais cite les sources de la crème solaire (S236, S237).
- **Roue et profil incohérents :** Gourmand pèse 35 % de la roue, mais aucun ingrédient du profil n'est de la famille Gourmand (Amyl Salicylate est Floral).
- **Clé mal écrite :** le modèle a rangé la note de tête sous `"tête"` (avec accent) et laissé `"tete"` vide. `verifier()` ne contrôle que `"tete"`, et l'application web lit `"tete"` : la note de tête est perdue côté application.

#### Texte : « L'odeur du marché de Thaïlande après une averse » (`POST /ask`)

<details>
<summary>Voir la réponse complète de l'API</summary>

```json
COLLE_ICI_LA_REPONSE_DE_L_API
```

</details>

**Évaluation complète : à lancer.** Les 29 cas, avec juge (~45 min) :

```bash
python eval_2.py --cas cas_test_2.json --juge qwen3.5:9b
```

Les fichiers `resultats_eval_ministral-3-8b.csv` (détail par cas) et `resume_eval_ministral-3-8b.md` (un tableau des 7 dimensions par route) remplaceront les résultats préliminaires ci-dessus.

## 5. API

FastAPI ([api.py](api.py)), port 8000. Swagger automatique sur `/docs`.

| Route | Clé | Rôle |
|---|---|---|
| `GET /health` | non | État : nombre de morceaux en base, modèles utilisés. |
| `POST /search` | oui | Les passages retrouvés seuls, sans appel au LLM. Entrée : `{question, top_k}`. |
| `POST /ask` | oui | L'analyse d'un souvenir texte. Entrée : `{question, top_k}` (`top_k` de 1 à 20, 4 par défaut). |
| `POST /ask_photo` | oui | L'analyse d'une photo, en `multipart/form-data` : `photo` (fichier) et `recit` (texte facultatif). |

**Contrat de `/ask`.** Sortie : `{question, answer, model, sources}`. `answer` contient toujours les clés `comprehension`, `signature`, `roue`, `profil`, `limites_catalogue`, `informations_manquantes`, `brief`. Si le LLM ne renvoie pas un JSON valide, `answer` est une chaîne de caractères. `/ask_photo` renvoie `{description_photo, resultat}`, où `resultat` suit le contrat de `/ask`.

| Code | Cause |
|---|---|
| 401 | En-tête `X-API-Key` absent ou faux |
| 422 | Corps invalide |
| 502 | Ollama injoignable, modèle absent ou génération interrompue |
| 503 | Base vide : lancer `python ingest.py` |

**Exemple réel** (C01, run du 12/11/2026, extrait de [evaluation_LLM/ask/resultats_eval_ministral-3-8b.csv](evaluation_LLM/ask/resultats_eval_ministral-3-8b.csv)). Souvenir : « J'étais en Thaïlande après la pluie, j'étais triste. »

```json
{
  "signature": {
    "nom": "Mélancolie des Temples",
    "description": "Une composition évoquant la solitude apaisante après la pluie en Thaïlande, mêlant l'encens des temples, la fraîcheur de la citronnelle et la douceur des fleurs tropicales…"
  },
  "roue": [
    { "famille": "Floral", "pourcentage": 30 },
    { "famille": "Green", "pourcentage": 20 },
    { "famille": "Woody", "pourcentage": 15 },
    { "famille": "Citrus", "pourcentage": 15 },
    { "famille": "Leather - Moss", "pourcentage": 10 },
    { "famille": "Herbal - Agrestic", "pourcentage": 10 }
  ],
  "profil": {
    "tete": [
      { "ingredient": "Methyl Heptenone Pure", "reference": "6937003",
        "raison": "notes fraîches et citronnées de citronnelle pour évoquer la pluie et l'air humide",
        "sources": ["S049", "S054"] }
    ],
    "coeur": [
      { "ingredient": "Jasmonyl™", "reference": "6346803",
        "raison": "jasmin pour évoquer les guirlandes des temples et la douceur nostalgique",
        "sources": ["S053", "S055", "S057"] }
    ],
    "fond": [
      { "ingredient": "Sandalore™", "reference": "8847801",
        "raison": "bois chaud et enveloppant pour rappeler la sensation de cocooning après la pluie",
        "sources": ["S246"] }
    ]
  }
}
```

(extrait : 1 ingrédient par niveau sur 2 ou 3 ; les autres clés sont toujours présentes)

**Accès.** Tunnel ngrok sur le domaine statique du compte : `https://bleach-handrail-driller.ngrok-free.dev` (Swagger : `/docs`). L'URL reste la même à chaque relance du tunnel. La clé d'API se transmet en privé, jamais dans le dépôt.

```bash
ngrok config add-authtoken <jeton du compte ngrok>   # une seule fois
ngrok http 8000
```

Le Wi-Fi de l'école bloque ngrok (`ERR_NGROK_8008`) : le tunnel passe par un partage de connexion 4G.

## 6. Intégration Tech

L'application web de l'équipe ([6OnTheBeach/hackathon-app](https://github.com/6OnTheBeach/hackathon-app)) appelle `POST {DATA_AI_URL}/ask` (fichier `api/src/modules/ai/ai.data.ts`).

| Élément | État au 12/11/2026 |
|---|---|
| Fournisseur `AI_PROVIDER=data` | En place dans hackathon-app ; `mock` par défaut pour développer sans ce service. |
| Contrat | Route, corps et format de `answer` identiques des deux côtés (types dans `api/src/modules/ai/ai.types.ts`). |
| URL | Transmise aux tech-leads : le domaine ngrok de la section 5. Premier appel réussi à travers le tunnel (`POST /ask 200`). |
| Clé d'API | Active côté Data/IA. Côté hackathon-app : en-tête `X-API-Key` et variable `DATA_AI_KEY` à ajouter. |
| Délai | L'application abandonne au bout de 120 s ; les analyses mesurées prennent 79 à 109 s (section 4). |

## 7. Limites

- **Lenteur :** 79 à 109 s par analyse sur le Mac de l'équipe, proche du délai maximum de l'application (120 s). Pistes : ministral-3:3b, `TOP_K` plus petit, réponses plus courtes.
- **Une seule machine :** le service tourne sur un Mac, exposé par ngrok. Il s'arrête avec le Mac, en veille ou hors connexion. L'application garde `AI_PROVIDER=mock` en repli.
- **Évaluation incomplète :** 3 cas mesurés sur 29 (section 4). La pertinence (LLM juge) n'est pas encore mesurée.
- **Injection de prompt :** S01 fait échouer la génération (HTTP 502) au lieu de produire une analyse normale.
- **Ingrédients à valider :** le profil est une piste construite à partir des notes olfactives du catalogue. Il doit être validé par un parfumeur ; les sources scientifiques ne citent pas ces ingrédients.
- **Catalogue limité :** 157 ingrédients, dont 54 Floral et seulement 2 Marine ; 96 descriptions tronquées sur le site source.
- **Fichiers manquants :** `sources_scent_journey.csv` (détail des sources S001 à S294, cité par la base) et `questions_test.csv` (nécessaire à `bench.py`) ne sont pas dans le dépôt.
- **Benchmark sur un autre document :** les mesures de la section 3 portent sur un document de démonstration, pas sur des souvenirs Scent Journey.
- **Vision :** le modèle est fixé dans [photo_vers_texte.py](photo_vers_texte.py) (`qwen2.5vl:7b`) ; la variable `VISION_MODEL` de [config.py](config.py) (`qwen2.5vl:3b`) n'est pas utilisée.
- **Traces du modèle de cours :** le Swagger et la collection ChromaDB parlent encore d'« histoire » (`story`). Sans effet sur le fonctionnement.

## 8. Tableau récapitulatif

| Livrable | Preuves dans le dépôt |
|---|---|
| 1. Données | [base_scent_journey.txt](base_scent_journey.txt), [catalogue_givaudan_complet.csv](catalogue_givaudan_complet.csv), [photo_test/](evaluation_LLM/ask_photo/photo_test/) |
| 2. Pipeline | [config.py](config.py), [ingest.py](ingest.py), [list.py](list.py), [clean.py](clean.py), [rag.py](rag.py), [requirements.txt](requirements.txt) |
| 3. Modèle | [benchmark_llm.pdf](benchmark_llm.pdf), [bench.py](bench.py), [api.py](api.py) (`SYSTEM_PROMPT`, `verifier()`), [photo_vers_texte.py](photo_vers_texte.py) |
| 4. Métriques | [eval_2.py](eval_2.py), [cas_test_2.json](cas_test_2.json), [evaluation_LLM/ask/](evaluation_LLM/ask/), [evaluation_LLM/ask_photo/](evaluation_LLM/ask_photo/) |
| 5. API | [api.py](api.py), Swagger `/docs` |

| Suivi | Lien |
|---|---|
| Dépôt Data/IA | https://github.com/danelquentin04/rag-g24 |
| Application web | https://github.com/6OnTheBeach/hackathon-app |
