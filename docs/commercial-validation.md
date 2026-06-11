# Validation commerciale et calibration V2

## Objet

Le workflow `pilot-evaluate` mesure les critères des Phases 1 à 3 de la roadmap :

- entretiens de découverte client ;
- pilotes Portfolio Screening ;
- vérité terrain et calibration du screening.

Il ne crée aucune preuve commerciale. Un fichier vide produit
`insufficient_evidence`. Aucun client, paiement, résultat de PTF ou avis opérateur
n'est déduit d'une donnée absente.

## Confidentialité

Les trois contrats utilisent des identifiants pseudonymes :

- `organization_id` au lieu du nom de l'entreprise ;
- `interview_id`, `pilot_id` et `client_site_id` sans information personnelle ;
- aucun nom, email, téléphone ou adresse personnelle.

Les fichiers réels ne doivent pas être committés. Les modèles sous
`examples/commercial_validation/` ne contiennent que les en-têtes.

## Commande

```bash
PYTHONPATH=src python -m thesegrid.cli pilot-evaluate \
  --interviews path/to/interviews.csv \
  --pilots path/to/pilots.csv \
  --ground-truth path/to/ground_truth.csv \
  --output results/commercial-validation
```

Sorties :

- `commercial_validation_summary.json` ;
- `commercial_validation_report.md` ;
- `interview_metrics.csv` ;
- `pilot_metrics.csv` ;
- `calibration_metrics.csv` ;
- `commercial_validation_manifest.json`.

Le manifest conserve le hash, la date de fichier, la date de lecture, le nombre de
lignes, les indicateurs de qualité, le rôle et la version de transformation de chaque
entrée.

## Entretiens

Segments acceptés :

- `developer_ipp` ;
- `grid_connection` ;
- `investor` ;
- `consultant` ;
- `aggregator_optimizer`.

Les booléens utilisent strictement `true` ou `false`. Un entretien marqué `completed`
doit renseigner toutes les réponses binaires.

Guide d'entretien :

1. Quel est le dernier site abandonné, retardé ou redimensionné, et pourquoi ?
2. Quelles étapes séparent l'identification foncière de la demande de PTF ?
3. Combien de sites sont étudiés pour un site finalement poursuivi ?
4. Quelles dépenses sont engagées avant d'avoir une information réseau suffisante ?
5. Quels outils, cartes, tableurs et prestataires sont utilisés aujourd'hui ?
6. Quelle preuve manque le plus souvent au moment de décider ?
7. Un classement portefeuille changerait-il l'ordre des dépenses ?
8. Quel résultat justifierait un Deep Dive ?
9. Qui achète, qui utilise et qui signe ?
10. Le résultat serait-il utilisé pour le foncier, la PTF, le comité
    d'investissement ou une acquisition ?
11. Le client partagerait-il un portefeuille anonymisé et son classement préalable ?
12. Accepterait-il un pilote, puis un pilote payant ?

La décision `go` exige simultanément :

- au moins 12 entretiens complets ;
- au moins 70 % classant le raccordement parmi les trois principaux risques ;
- au moins 50 % ayant subi une perte liée à une information réseau tardive ;
- cinq portefeuilles partageables ;
- trois intérêts pilote ;
- deux intérêts pilote payant.

Le rapport suit aussi les objectifs d'échantillonnage : 8 développeurs/IPP, 3
responsables raccordement, 3 investisseurs, 3 consultants et 2
agrégateurs/optimisateurs. Ces objectifs décrivent la couverture souhaitée ; les six
critères ci-dessus restent le gate `go`.

Après au moins 12 entretiens, la décision devient `no-go` si aucun budget n'existe, si
tous les outils internes sont jugés suffisants, si toutes les décisions dépendent
d'informations privées indisponibles, ou si personne n'accepte la comparaison aux
décisions passées.

## Pilotes

Chaque ligne représente un portefeuille de 20 à 100 sites.

Principales règles :

- `agreement_signed`, `anonymized_metrics_allowed` et `sources_frozen` doivent être
  vrais ;
- le classement préalable du client doit être obtenu avant restitution ;
- les décisions à 30 jours doivent être enregistrées ;
- `delivery_working_days` mesure le délai de service ;
- un pilote payant exige `billed_eur > 0` ;
- `collected_eur` ne peut pas dépasser `billed_eur` ;
- les coûts des pilotes gratuits restent inclus dans la marge globale ;
- les compteurs de correction, compréhension et changement ne peuvent pas dépasser
  leurs dénominateurs.

Marge brute :

```text
billed_eur
- human_hours * labor_cost_eur_per_hour
- other_cost_eur
```

Le succès exige trois pilotes, deux facturés, moins de 10 % de corrections d'identité,
au moins 80 % de recommandations compréhensibles, au moins 30 % de sites repriorisés,
un passage en Deep Dive par pilote, deux demandes de réutilisation et une marge totale
positive. Il exige aussi que tous les accords, droits de métriques anonymisées, gels de
sources, classements préalables et suivis à 30 jours soient présents.

## Vérité terrain

Types de preuve :

- `none` ;
- `deep_dive` ;
- `consultant` ;
- `exploratory_study` ;
- `ptf` ;
- `operator`.

Résultats :

- `viable` ;
- `conditional` ;
- `not_viable` ;
- `inconclusive` ;
- `pending`.

Classes A/B : prédiction positive. Classes C/D : prédiction négative.
`viable` et `conditional` sont des résultats positifs ; `not_viable` est négatif.
Les résultats `inconclusive` et `pending` sont exclus de la matrice de confusion.
Lorsque `deep_evidence_type=none`, seuls `inconclusive` et `pending` sont acceptés.

La calibration devient éligible seulement après :

- 50 sites revus professionnellement ;
- 15 sites avec preuve plus profonde ;
- deux régions ;
- deux niveaux de tension.

Le workflow calcule précision, rappel, faux positifs et faux négatifs. Il ne modifie pas
automatiquement les seuils de `portfolio-geospatial-v1`.
