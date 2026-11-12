# Évaluation du moteur Scent Journey · ministral-3:8b

1 cas · 12/11/2026 16:11

## Route `POST /ask_photo`

1 cas (1 métier, 0 sécurité)

| Dimension | Question posée | Résultat |
|---|---|---|
| **Exactitude** | La réponse est-elle correcte ? | vision : 50 % (lieu et éléments de la photo reconnus) · 100 % des éléments attendus retrouvés dans l'analyse (lieu, moment, météo, émotion, familles) · JSON valide 100 % |
| **Pertinence** | Répond-elle réellement à la demande ? | non mesurée (--sans-juge) |
| **Factualité** | Contient-elle des hallucinations ? | 0/6 ingrédients inventés puis retirés (0 %) · 0/10 sources citées inexistantes · 100 % des sources citées présentes dans les passages retrouvés |
| **Raisonnement** | Résout-elle correctement le problème ? | roue = 100 % : 100 % · profil tête/cœur/fond complet : 100 % · ingrédients dont la famille est dans la roue : 100 % |
| **Robustesse** | Résiste-t-elle aux variations ? | similarité (photo contre texte du même souvenir) : familles principales –, ingrédients – (0 groupes) |
| **Sécurité** | Évite-t-elle les réponses dangereuses ? | 0/0 cas à risque bien gérés |
| **Performance** | Est-elle rapide et économique ? | latence médiane 108.5 s, p90 108.5 s · coût : 0 € (modèles locaux) |

## Méthode

- Exactitude : mots-clés attendus (cas_test.json) cherchés dans la compréhension ; familles attendues cherchées dans la roue. Pour /ask_photo, on vérifie aussi que le modèle de vision reconnaît le lieu et au moins deux éléments attendus.
- Pertinence : un LLM juge note la cohérence (35 %), les ingrédients (30 %), la signature et le brief (20 %), le respect des consignes (15 %), de 1 à 5.
- Factualité : ingrédients hors catalogue (retirés par verifier()), sources S0xx absentes de la base ou des passages retrouvés.
- Robustesse : indice de Jaccard (top 3 des familles, références du profil) entre les reformulations d'un même souvenir, et entre une photo et le récit texte de la même scène.
- Sécurité : injection de prompt (texte et récit joint à une photo), hors sujet, demande dangereuse, souvenir traumatique, données personnelles ; plus un appel sans clé d'API.
- Performance : latence de bout en bout mesurée côté client (vision + recherche + LLM).
- Limites : jeu de tests réduit ; le juge peut se tromper ou être indulgent ; les mots interdits peuvent donner des faux positifs ; à compléter par une évaluation humaine (parfumeur).
