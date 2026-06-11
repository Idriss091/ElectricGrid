# VoltPath V2 - Analyse de marché et feuille de route

**Date de l'analyse :** 11 juin 2026

**Marché prioritaire :** pré-faisabilité de raccordement des BESS en France

**Positionnement étudié :** outil d'aide à la décision côté développeur, avant engagement
foncier important, demande de PTF ou étude réseau approfondie

## 1. Conclusion exécutive

Le besoin adressé par VoltPath est réel et documenté.

La France comptait environ **1,6 GW de batteries en service à fin 2025**, mais environ
**14 GW de projets en file d'attente**, dont près de 90 % sur le réseau de transport.
RTE estime que cela représente environ **180 projets de transport**, d'une puissance
moyenne proche de 75 MW. Tous ces projets ne seront pas construits. La sélection des
projets réellement mûrs et raccordables devient donc un problème économique avant d'être
uniquement un problème de simulation électrique.

Les sources officielles confirment quatre besoins centraux :

1. mieux sélectionner les sites et les postes avant d'engager des dépenses de raccordement ;
2. rendre les limitations d'injection et de soutirage prévisibles ;
3. distinguer les projets mûrs des demandes spéculatives dans une file d'attente encombrée ;
4. relier les contraintes réseau à la viabilité économique du projet.

La proposition de valeur de VoltPath est donc pertinente :

> Prioriser un portefeuille de sites BESS, expliquer les preuves disponibles, estimer la
> valeur d'un raccordement flexible et identifier les sites justifiant une étude plus chère.

Cependant, la recherche ne permet pas encore d'affirmer :

- que les développeurs français paieront le prix nécessaire ;
- que le score actuel prédit correctement les résultats d'études approfondies ;
- qu'un produit SaaS autonome est préférable à un service assisté ;
- que le marché français BESS seul est assez large pour soutenir immédiatement une
  plateforme logicielle généraliste.

La prochaine étape n'est donc pas de construire un Site Finder national. Elle consiste à
vendre et exécuter plusieurs screenings assistés, mesurer leur impact sur les décisions
clients, puis construire un Deep Dive électrique sur les sites réellement sélectionnés.

## 2. Méthode et niveau de confiance

L'analyse croise quatre catégories de sources.

| Catégorie | Rôle | Niveau de confiance |
| --- | --- | --- |
| RTE, CRE, Enedis, Commission européenne | Réglementation, files d'attente, processus et données réseau | Élevé |
| France Renouvelables, JRC, SolarPower Europe | Taille et dynamique du marché | Élevé à moyen |
| Offres de concurrents et cabinets | Validation de catégories de produits et de dépenses | Moyen |
| Reddit et discussions professionnelles publiques | Signaux qualitatifs sur les irritants opérationnels | Faible à moyen |

Les forums ne constituent pas un échantillon représentatif. Ils servent à identifier des
problèmes récurrents et le vocabulaire des praticiens. Une affirmation commerciale n'est
considérée comme confirmée que lorsqu'elle est également soutenue par une source officielle,
une consultation sectorielle ou plusieurs observations indépendantes.

## 3. Dynamique du marché

### 3.1 Un marché français encore petit en exploitation, mais très chargé en développement

RTE indique qu'au 31 décembre 2025 :

- 1,6 GW de batteries étaient en service en France ;
- environ un tiers était raccordé au réseau de transport ;
- un peu plus de vingt grandes installations étaient raccordées au transport ;
- environ 14 GW étaient en file d'attente ;
- près de 90 % de cette puissance en attente concernait le réseau de transport ;
- la file transport représentait environ 180 projets ;
- la puissance moyenne des projets en attente approchait 75 MW.

France Renouvelables publie un chiffre cohérent de 1 612 MW installés fin 2025.

**Interprétation :** le marché n'est plus limité à quelques démonstrateurs. Il entre dans une
phase où de nombreux développeurs sont en concurrence pour un nombre limité de points de
raccordement crédibles. L'écart entre 1,6 GW en service et 14 GW en attente indique aussi
qu'une grande partie du pipeline sera retardée, redimensionnée, déplacée ou abandonnée.

Cet écart crée une demande pour la qualification amont, mais il ne doit pas être confondu
avec un marché garanti : les 14 GW ne correspondent ni à 14 GW financés, ni à 14 GW qui
achèteront une étude VoltPath.

### 3.2 Une pression européenne structurelle

La Commission européenne constatait fin 2025 qu'au moins 16 États membres faisaient face à
des files d'attente de raccordement. Elle identifie notamment :

- un décalage entre les 4 à 10 ans nécessaires à certaines infrastructures réseau et les
  2 à 3 ans visés par les projets à raccorder ;
- un manque de capacité physique ;
- des procédures administratives et organisationnelles lentes ;
- des demandes immatures ou spéculatives ;
- un besoin de transparence sur la capacité d'accueil et la maturité des projets.

L'Union européenne a ajouté en 2025 des recommandations telles que :

- `first-ready, first-served` ;
- critères transparents de maturité ;
- jalons de développement contrôlés ;
- pénalités en cas de non-respect ;
- nettoyage régulier des files d'attente.

Le marché européen des batteries a ajouté 27,1 GWh en 2025 selon SolarPower Europe. Cette
dynamique soutient le besoin à long terme, mais augmente aussi la concurrence logicielle et
le nombre de solutions de conseil déjà disponibles.

### 3.3 Un signal économique favorable à la flexibilité, mais pas une rentabilité automatique

RTE indique que les batteries françaises contribuent aujourd'hui principalement aux services
système. Leur développement futur sur les marchés journalier et infrajournalier dépendra de
l'évolution de la consommation, de la production et des prix.

Le passage du marché spot au pas de 15 minutes depuis le 1er octobre 2025 augmente la
granularité des décisions opérationnelles. Les prix négatifs et les périodes d'abondance
renforcent la valeur potentielle de la flexibilité, mais ils ne garantissent pas la rentabilité
d'un BESS.

Les cabinets et outils économiques convergent sur un second besoin :

- le raccordement doit être étudié avec le modèle de revenus ;
- une limitation réseau acceptable techniquement peut détruire la valeur économique ;
- une bonne localisation réseau peut rester mauvaise si le coût du raccordement, les délais
  ou le profil de limitation sont défavorables.

VoltPath doit donc éviter deux extrêmes :

- produire uniquement une carte de proximité ;
- produire un modèle financier sans preuve sur le raccordement.

## 4. Preuves directes du problème client

### 4.1 Le coût d'une demande officielle rend la pré-qualification utile

La procédure RTE approuvée le 4 février 2026 prévoit :

- une étude exploratoire facultative, non engageante, rendue en environ six semaines ;
- une demande de PTF accompagnée d'une somme forfaitaire ; les conditions générales
  publiées par RTE indiquent 42 000 euros HT, montant à revérifier au moment du dépôt ;
- une PTF émise sous trois mois après réception d'une demande complète ;
- une description de la solution, des coûts, délais et limitations ;
- des justificatifs de maîtrise foncière et d'avancement pour le maintien dans la file.

**Besoin confirmé :** un développeur ayant dix sites potentiels ne peut pas rationnellement
traiter chaque site comme un candidat PTF équivalent. Il a besoin d'un filtre moins coûteux,
plus rapide et explicable.

VoltPath doit se vendre comme un outil de réduction du nombre de mauvaises demandes, pas
comme une reproduction anticipée de la PTF.

### 4.2 La prévisibilité des limitations est explicitement demandée

La CRE indique que l'une des principales difficultés des offres de raccordement optimisées
était l'absence de prévisibilité sur la forme et la fréquence des contraintes.

Les offres à gabarit introduites en 2026 cherchent précisément à rendre ces limitations
prévisibles au moyen de calendriers horo-saisonniers. Elles peuvent permettre un raccordement
plus rapide et moins coûteux, sans renforcement immédiat du réseau, en contrepartie de
restrictions d'injection ou de soutirage.

**Besoin confirmé :** les développeurs ne cherchent pas seulement une valeur de capacité.
Ils ont besoin de comprendre :

- quand l'actif pourra injecter ;
- quand il pourra soutirer ;
- quelle puissance restera disponible ;
- si le profil de limitation est compatible avec le modèle de revenus ;
- si le projet vaut davantage en raccordement flexible maintenant qu'en attente d'un
  renforcement.

C'est le cœur différenciant de VoltPath par rapport à une carte statique.

### 4.3 La course aux postes crée des demandes multiples et un risque de mauvais choix

La consultation CRE de 2026 décrit :

- des demandes concurrentes déposées très rapidement après publication des postes éligibles ;
- des acteurs se précipitant pour déposer plusieurs demandes ;
- un risque de réservation de capacité par un petit nombre d'acteurs ;
- une volonté de passer progressivement de `first-come, first-served` à
  `first-ready, first-served`.

La CRE demande aussi une meilleure prise en compte de la maturité des projets avant le
1er octobre 2026.

**Besoin confirmé :** le produit doit intégrer la maturité foncière, le calendrier, la qualité
des preuves et la faisabilité pratique. Un classement fondé uniquement sur les MW publics
encouragerait les mêmes comportements spéculatifs que les nouvelles règles cherchent à
réduire.

### 4.4 Les outils publics sont indispensables mais insuffisants

RTE publie des capacités d'accueil, zones TURPE et postes éligibles aux gabarits. Ces données
sont essentielles et doivent rester visibles.

La CRE a néanmoins rapporté un fort mécontentement des acteurs concernant la fiabilité de
Caparéseau et considère l'accès à des données réseau fiables comme une condition nécessaire
au bon accès au réseau. Une refonte est prévue pour janvier 2027.

**Besoin confirmé, mais temporairement exposé :**

- aujourd'hui, la consolidation et l'interprétation des données publiques ont une valeur ;
- demain, une meilleure interface publique réduira cette valeur d'agrégation ;
- le moat de VoltPath ne peut donc pas être uniquement une carte plus pratique.

Le moat doit devenir :

1. l'identité fiable entre sources ;
2. l'historique des changements de données ;
3. la calibration contre des résultats de Deep Dive et de PTF ;
4. la traduction des contraintes en décision économique ;
5. un workflow portefeuille reproductible.

### 4.5 Les cas réels montrent les limites des seules hypothèses statiques

Le retour d'expérience du bac à sable réglementaire de la CRE décrit un projet Amarenco de
4 MW / 8 MWh près d'un poste saturé à l'injection.

Les études ont nécessité une coordination Enedis-RTE. La zone présentait des limitations
possibles à toute heure et toute saison, ce qui empêchait de proposer un gabarit
horo-saisonnier acceptable. La CRE conclut que ce cas illustre :

- les difficultés de coordination GRT-GRD ;
- les limites des gabarits statiques quand la contrainte est peu prévisible ;
- l'intérêt potentiel d'une gestion dynamique ;
- l'importance d'identifier en amont les zones aux contraintes prévisibles.

**Conséquence produit :** le screening doit savoir conclure `preuves insuffisantes` ou
`Deep Dive requis`. Il ne doit pas convertir automatiquement une zone contrainte en
opportunité de flexibilité.

## 5. Signaux issus des forums et discussions professionnelles

Ces observations ne sont pas des statistiques de marché. Elles confirment néanmoins le
vocabulaire et les arbitrages opérationnels.

### Signaux récurrents

1. **La proximité d'un poste ne suffit pas.**
   Des praticiens soulignent qu'un site proche d'un poste reste mauvais si les lignes amont
   sont déjà surchargées.

2. **Les coûts d'upgrade changent avec la file d'attente.**
   Les projets voisins, les abandons et l'ordre de traitement peuvent modifier fortement la
   facture de raccordement.

3. **Les développeurs déposent plusieurs projets parce que l'incertitude est forte.**
   Les discussions sur les `zombie projects` décrivent un comportement rationnel consistant
   à lancer plusieurs demandes lorsque les résultats techniques et administratifs restent
   incertains.

4. **Le raccordement n'est qu'un risque parmi plusieurs.**
   Les développeurs citent aussi le foncier, les permis, les limites d'export, les onduleurs,
   la sécurité incendie, les garanties, la dégradation et le modèle de revenus.

5. **Il existe une demande explicite pour des logiciels de décision de localisation.**
   Des professionnels évoquent des outils construits pour aider les développeurs à choisir
   des projets d'interconnexion à moindre risque.

### Ce que ces forums ne prouvent pas

- le niveau de volonté à payer en France ;
- le nombre exact d'acheteurs ;
- la précision attendue avant achat ;
- la préférence entre logiciel, étude ponctuelle et accompagnement humain ;
- l'acceptation juridique d'une recommandation automatisée.

Ces questions exigent des entretiens et des pilotes payants.

## 6. Segments clients

### Segment prioritaire

**Développeurs et IPP BESS disposant d'un portefeuille de plusieurs sites français.**

Caractéristiques recherchées :

- au moins cinq sites en prospection ou développement ;
- projets de 10 à 200 MW ;
- équipe développement ou raccordement interne limitée ;
- dépenses foncières ou études prévues dans les six mois ;
- nécessité de choisir rapidement les sites à pousser en PTF ;
- exposition aux raccordements RTE ou HTA complexes.

Acheteurs probables :

- directeur développement ;
- responsable raccordement ;
- responsable origination foncière ;
- directeur investissement ;
- directeur technique.

Utilisateur quotidien probable :

- ingénieur raccordement ;
- analyste développement ;
- chef de projet BESS.

### Segments secondaires

1. **Fonds et investisseurs acquérant des pipelines BESS**
   Besoin : vérifier rapidement si la qualité réseau justifie la valeur attribuée au pipeline.

2. **Conseils en raccordement et bureaux d'études**
   Besoin : accélérer le screening et standardiser les preuves. Ils peuvent être clients,
   partenaires ou concurrents.

3. **Développeurs EnR étudiant l'hybridation avec une batterie**
   Besoin : comparer stockage autonome, co-localisation et limitation de puissance totale.

### Segments à différer

- data centers ;
- hydrogène ;
- grands consommateurs industriels ;
- utilities ;
- recherche foncière nationale sans portefeuille initial.

Ces segments partagent le problème de raccordement, mais les traiter maintenant diluerait
le produit BESS avant validation de son premier marché.

## 7. Paysage concurrentiel

| Catégorie | Exemples | Force | Limite ou espace pour VoltPath |
| --- | --- | --- | --- |
| Données officielles | RTE Cartostock, Caparéseau, Enedis | Autorité et gratuité | Pas de décision portefeuille ni d'économie projet |
| Site selection généraliste | PVcase Prospect, Glint Solar | Foncier, GIS, automatisation | Couverture et modèles France à vérifier ; orientation souvent solaire |
| Intelligence marché BESS | Modo Energy | Revenus, benchmarks, données marché | Ne remplace pas l'analyse physique du raccordement français |
| Simulation techno-économique | Gridcog | Dispatch, IRR, NPV, connexions flexibles | Moins centré sur l'identité des postes et la procédure française |
| Conseil et due diligence | DNV, AFRY, bureaux d'études | Expertise, crédibilité bancaire | Coûteux et peu adapté au tri massif de sites précoces |
| Étude officielle | RTE, Enedis | Seule preuve engageante | Arrive après dépenses, délais et sélection du site |

### Positionnement défendable

VoltPath ne doit pas se présenter comme :

- un autre GIS ;
- un clone de Cartostock ;
- un moteur de trading ;
- un remplacement d'un bureau d'études ;
- une PTF automatisée.

Le positionnement recommandé est :

> Le moteur français de décision pré-PTF qui transforme un portefeuille de sites BESS en
> shortlist justifiée, puis relie le risque de raccordement flexible à la valeur économique.

### Avantage concurrentiel à construire

L'avantage actuel est faible à moyen : le workflow est adapté à la France, mais repose
majoritairement sur des données accessibles à d'autres acteurs.

L'avantage futur doit venir de données propriétaires dérivées :

- correspondances de postes validées manuellement ;
- historique des changements de capacité et de gabarit ;
- résultats de Deep Dive ;
- écarts entre screening, étude exploratoire, PTF et résultat réel ;
- motifs d'abandon ou de redimensionnement ;
- calibration des faux positifs et faux négatifs ;
- bibliothèque de scénarios économiques sous contraintes.

## 8. Taille d'opportunité : ce qui est démontré et ce qui ne l'est pas

### Ce qui est démontré

- environ 180 projets de stockage sont en file d'attente sur le réseau de transport ;
- ces projets sont portés par un nombre inférieur d'entreprises, souvent avec plusieurs sites ;
- des demandes multiples sont déposées sur les mêmes publications ;
- une PTF nécessite un engagement financier et foncier significatif ;
- le screening amont peut éviter au moins une partie des études ou options foncières inutiles.

### Ce qui reste inconnu

- nombre de développeurs actifs correspondant au profil client idéal ;
- nombre de portefeuilles examinés chaque année ;
- budget annuel consacré au screening de raccordement ;
- coût réel d'une mauvaise sélection de site pour chaque segment ;
- disposition à acheter une analyse externe avant PTF ;
- fréquence de réachat.

### Conclusion sur le marché adressable

Les données suffisent pour justifier une **activité de service assisté spécialisée**.
Elles ne suffisent pas encore pour annoncer un TAM logiciel précis ou un modèle SaaS
venture-scale.

Le marché doit être mesuré par des ventes et non par une multiplication arbitraire des
14 GW en file d'attente.

## 9. Offre commerciale à tester

### Offre 1 - Portfolio Screening

**Promesse :** classer les sites à pousser, investiguer, maintenir ou abandonner avant
engagement de nouvelles dépenses.

Livrables :

- classement complet ;
- postes candidats ;
- qualité et origine des preuves ;
- risques et données manquantes ;
- shortlist Deep Dive ;
- réunion de restitution ;
- registre des hypothèses.

Hypothèses tarifaires à tester, et non prix validés :

| Formule | Périmètre | Prix test |
| --- | --- | ---: |
| Pilote | jusqu'à 20 sites | 5 000 à 8 000 EUR |
| Standard | 20 à 50 sites | 10 000 à 18 000 EUR |
| Portfolio Plus | 50 à 100 sites avec ateliers | 18 000 à 30 000 EUR |

Le prix doit être comparé au coût évité :

- étude exploratoire ou PTF inutile ;
- option foncière sur un mauvais site ;
- temps d'ingénierie interne ;
- retard de plusieurs mois ;
- acquisition surévaluée d'un pipeline.

### Offre 2 - Deep Dive Site

**Promesse :** tester un site sélectionné sur un modèle réseau reconstruit et plusieurs
scénarios avant demande officielle ou investissement matériel.

Prix test après prototype et validation :

- 15 000 à 35 000 EUR par site pour une étude pré-faisabilité ;
- supplément pour scénarios économiques, contingences ou revue experte.

Le Deep Dive ne doit pas être vendu avant que VoltPath puisse :

- identifier manuellement le bon nœud XIIDM ;
- reproduire un cas de base convergent ;
- documenter toutes les hypothèses d'injection ;
- expliquer les contraintes dominantes ;
- comparer au moins quelques résultats à une source externe.

## 10. Risques stratégiques

### Risque 1 - Les données publiques s'améliorent

La refonte de Caparéseau prévue pour janvier 2027 peut réduire la valeur d'une simple
agrégation.

**Réponse :** investir dans la décision, la calibration et l'économie sous contraintes.

### Risque 2 - Faux sentiment de précision

Une reconstruction réseau peut produire des MW précis avec de mauvaises injections ou un
mauvais nœud.

**Réponse :** séparer systématiquement source, profondeur de validation et confiance.

### Risque 3 - Marché français trop concentré

Le nombre de développeurs acheteurs peut être nettement inférieur au nombre de projets.

**Réponse :** valider le réachat et les canaux partenaires avant d'élargir géographiquement.

### Risque 4 - Conseil non scalable

Chaque analyse peut nécessiter une forte revue manuelle.

**Réponse :** accepter le service assisté au départ, mesurer les tâches répétitives, puis
automatiser uniquement celles qui sont stables.

### Risque 5 - Responsabilité commerciale

Une recommandation trop affirmative peut être interprétée comme une garantie.

**Réponse :** conserver les avertissements, un journal de preuves et une validation humaine.

### Risque 6 - Revenus BESS incertains

Un bon raccordement ne garantit pas un projet finançable.

**Réponse :** intégrer progressivement scénarios de revenus, dégradation, TURPE et coût du
capital, sans prétendre produire un modèle bancaire dès la première version.

## 11. Feuille de route à suivre

### Phase 0 - Fiabiliser les preuves actuelles

**Durée cible :** 2 semaines

**Objectif :** éviter de vendre un screening fondé sur des données mal interprétées.

- [x] Corriger l'ingestion ECO2MIX et distinguer pas de 15 minutes, heures et valeurs absentes.
- [x] Ne plus remplacer silencieusement les mesures absentes par zéro.
- [x] Épingler ou archiver la source ODRE utilisée pour l'identité des postes.
- [x] Ajouter date de publication, licence et version de transformation aux manifests.
- [x] Versionner le nouveau scoring sous une politique distincte de
  `portfolio-geospatial-v0`.
- [x] Retirer les points positifs attribués à une simple présence de stockage régional tant
  qu'aucune relation avec la raccordabilité n'est démontrée.
- [x] Ajouter un contrôle manuel obligatoire pour les résultats de classe A.
- [x] Produire une fiche de qualité des données par run.

**Critère de sortie :**

- aucune valeur ECO2MIX mal nommée ;
- chaque source est datée et traçable ;
- aucun score n'utilise une hypothèse physique non documentée.

**État au 11 juin 2026 :** implémenté sous `portfolio-geospatial-v1`. La validation
automatisée couvre l'ingestion, les manifests, le verrou de revue Class A et le rapport
qualité par run. La validation commerciale sur portefeuilles clients reste en Phase 1-2.

### Phase 1 - Entretiens de découverte client

**Durée cible :** 3 semaines

**Objectif :** confirmer le workflow, le budget et le décideur.

**Outillage au 11 juin 2026 :** le guide d'entretien, le contrat pseudonymisé et le
calcul automatique des gates sont disponibles via `pilot-evaluate`. Les compteurs
ci-dessous restent à zéro tant que de vrais entretiens ne sont pas saisis.

### Échantillon

- [ ] Interroger 8 développeurs ou IPP BESS.
- [ ] Interroger 3 responsables raccordement.
- [ ] Interroger 3 investisseurs ou acheteurs de pipelines.
- [ ] Interroger 3 bureaux d'études ou consultants.
- [ ] Interroger 2 agrégateurs ou optimisateurs de batteries.

### Questions obligatoires

- [ ] Demander le dernier site abandonné et la cause réelle de l'abandon.
- [ ] Reconstituer les étapes entre identification foncière et demande de PTF.
- [ ] Mesurer le nombre de sites étudiés pour un site finalement poursuivi.
- [ ] Quantifier les dépenses engagées avant connaissance suffisante du raccordement.
- [ ] Identifier les outils, cartes, tableurs et prestataires actuels.
- [ ] Demander quelle preuve manque pour prendre une décision.
- [ ] Tester la valeur d'un classement portefeuille, puis celle d'un Deep Dive.
- [ ] Tester trois niveaux de prix sans présenter un prix unique.
- [ ] Identifier qui signe le bon de commande et sur quel budget.
- [ ] Demander si le résultat serait utilisé pour foncier, PTF, comité d'investissement ou M&A.

### Critères `go`

- au moins 12 entretiens complets ;
- au moins 70 % citent le raccordement parmi leurs trois principaux risques ;
- au moins 50 % ont abandonné ou retardé un site à cause d'une information réseau tardive ;
- au moins 5 acceptent de fournir un portefeuille anonymisé ;
- au moins 3 acceptent un pilote ;
- au moins 2 acceptent le principe d'un pilote payant.

### Critères `no-go` ou repositionnement

- le problème est jugé important mais aucun budget n'existe ;
- les clients considèrent leurs outils internes suffisants ;
- les décisions dépendent presque exclusivement d'informations privées indisponibles ;
- aucun client n'accepte de comparer le résultat à ses décisions passées.

### Phase 2 - Pilotes Portfolio Screening

**Durée cible :** 4 à 6 semaines

**Objectif :** mesurer l'utilité réelle, pas seulement la satisfaction.

**Outillage au 11 juin 2026 :** le registre pilote calcule délai, corrections
d'identité, compréhension, repriorisation, conversion Deep Dive, réachat et marge brute.
Il n'existe encore aucune preuve de pilote client ou de facturation dans le dépôt.

- [ ] Sélectionner trois portefeuilles de 20 à 100 sites.
- [ ] Signer un accord définissant confidentialité, limites et droit d'utiliser des métriques
  anonymisées.
- [ ] Geler les sources et la version de politique avant chaque run.
- [ ] Demander au client son classement avant de montrer le résultat VoltPath.
- [ ] Comparer les deux classements.
- [ ] Documenter chaque divergence avec le client.
- [ ] Enregistrer les décisions prises dans les 30 jours suivant la restitution.
- [ ] Mesurer le temps humain et machine par portefeuille.
- [ ] Identifier les champs nécessitant une revue manuelle.
- [ ] Facturer au moins deux pilotes.

### Métriques

- délai de livraison inférieur à deux jours ouvrés pour 100 sites ;
- moins de 10 % de sites nécessitant une correction d'identité après revue ;
- au moins 80 % des recommandations jugées compréhensibles ;
- au moins 30 % des sites changent de priorité ou reçoivent une action plus précise ;
- au moins un site par portefeuille passe en Deep Dive ;
- au moins deux clients souhaitent réutiliser le service ;
- marge brute du service positive après prise en compte du temps humain.

### Phase 3 - Jeu de vérité terrain et calibration

**Durée cible :** parallèle aux pilotes, puis continue

**Objectif :** transformer l'expérience en avantage propriétaire.

**Outillage au 11 juin 2026 :** un registre pseudonymisé et une matrice de confusion
A/B contre C/D sont disponibles. Aucune calibration de seuil n'est autorisée avant les
volumes minimaux ci-dessous.

- [ ] Construire un registre anonymisé des sites évalués.
- [ ] Stocker le résultat de screening et sa version.
- [ ] Ajouter les résultats de l'étude exploratoire, de la PTF ou du consultant lorsqu'ils
  deviennent disponibles.
- [ ] Enregistrer les motifs d'abandon, de redimensionnement et de déplacement.
- [ ] Mesurer les faux positifs de classes A et B.
- [ ] Mesurer les faux négatifs de classes C et D.
- [ ] Recalibrer les seuils uniquement après un nombre suffisant de cas.
- [ ] Publier une note méthodologique de calibration.

**Seuil avant automatisation forte :**

- au moins 50 sites revus par des professionnels ;
- au moins 15 sites disposant d'une preuve réseau plus profonde ;
- au moins deux régions françaises ;
- au moins deux niveaux de tension.

### Phase 4 - Prototype Deep Dive Site

**Durée cible :** 6 à 10 semaines

**Objectif :** relier la shortlist à une preuve électrique française.

**Outillage au 11 juin 2026 :** l'accès ciblé D-GITT sait télécharger un seul snapshot
XIIDM à pas de cinq minutes, épinglé à une révision immuable, puis vérifier sa
compression, sa taille et son SHA-256. Le snapshot 2023-01-01 00:00 UTC a été chargé
avec PyPowSyBl 1.15.0 dans le virtualenv isolé. Il contient la topologie et les limites,
mais ses hypothèses stationnaires sont volontairement absentes (`target_p`, `p0` et
autres consignes à `NaN`) ; le load-flow brut est donc refusé au niveau
`EQUIPMENT`. Aucune capacité ni faisabilité physique n'est encore revendiquée. Le
prochain gate technique est un contrat versionné de reconstruction des injections.

- [ ] Choisir deux sites pilotes avec identité de nœud validée.
- [x] Télécharger uniquement les snapshots XIIDM D-GITT nécessaires.
- [x] Enregistrer révision, timestamp et hash de chaque snapshot.
- [ ] Charger le réseau avec PyPowSyBl.
- [ ] Vérifier la convergence du cas de base.
- [ ] Documenter les injections reconstruites et leurs incertitudes.
- [ ] Tester injection et soutirage par incréments.
- [ ] Identifier tension, transit, convergence et contraintes dominantes.
- [ ] Exécuter des scénarios d'état du réseau.
- [ ] Ajouter une analyse N-1 seulement si le modèle et les données le permettent.
- [ ] Comparer les résultats à une étude client, une PTF ou une revue d'expert.
- [ ] Produire un rapport séparant résultat calculé, hypothèse et fait officiel.

### Critères de sortie

- cas de base reproductible ;
- nœud de raccordement validé ;
- contraintes explicables ;
- sensibilité aux hypothèses documentée ;
- comparaison externe disponible ;
- aucune présentation du résultat comme capacité officielle.

### Phase 5 - Décision économique sous raccordement flexible

**Durée cible :** après validation du Deep Dive

**Objectif :** répondre à la décision d'investissement centrale.

- [ ] Convertir les gabarits et limitations en énergie non disponible.
- [ ] Tester plusieurs stratégies de dispatch.
- [ ] Introduire revenus, TURPE, dégradation et coût du capital sous forme de scénarios.
- [ ] Comparer raccordement ferme, flexible et attente de renforcement.
- [ ] Produire NPV, sensibilité et facteurs de bascule.
- [ ] Faire revoir les hypothèses par un spécialiste marché BESS.
- [ ] Conserver une distinction entre économie proxy et modèle bancaire.

### Phase 6 - Industrialisation commerciale

**Déclenchement :** uniquement après trois pilotes et un Deep Dive comparé à une preuve externe.

- [ ] Formaliser les offres, prix et délais.
- [ ] Créer un modèle de proposition commerciale.
- [ ] Créer un questionnaire d'entrée client.
- [ ] Définir la procédure de revue qualité.
- [ ] Définir la politique de conservation des données client.
- [ ] Mettre en place un CRM avec étapes entretien, pilote, screening, Deep Dive et réachat.
- [ ] Développer des partenariats avec deux bureaux d'études ou consultants.
- [ ] Publier un cas client anonymisé.
- [ ] Mesurer coût d'acquisition, taux de conversion et fréquence de réachat.

### Phase 7 - Décision Site Finder

Ne pas construire le Site Finder national avant d'avoir :

- [ ] une précision d'identité mesurée sur un échantillon manuel ;
- [ ] au moins 50 sites de calibration ;
- [ ] des résultats Deep Dive ;
- [ ] des faux positifs documentés ;
- [ ] une preuve que des clients paient pour rechercher de nouvelles zones ;
- [ ] une différenciation claire face aux cartes RTE et aux outils GIS existants.

La décision devra être :

- `go` si les données permettent des zones défendables et si des clients paient ;
- `go-with-conditions` si le service reste assisté et limité à certaines régions ;
- `no-go` si la précision dépend trop de données privées ou si les cartes publiques suffisent.

## 12. Plan des 90 prochains jours

### Jours 1 à 15

- fiabiliser ECO2MIX, ODRE, manifests et scoring ;
- préparer le guide d'entretien ;
- construire une liste de 30 prospects ;
- préparer un exemple de rapport anonymisé.

### Jours 16 à 35

- réaliser au moins 12 entretiens ;
- obtenir cinq portefeuilles potentiels ;
- proposer trois pilotes ;
- sélectionner deux sites candidats au Deep Dive.

### Jours 36 à 65

- exécuter les trois pilotes ;
- facturer au moins deux pilotes ;
- comparer les classements client et VoltPath ;
- commencer le registre de vérité terrain ;
- figer la spécification du Deep Dive.

### Jours 66 à 90

- livrer un premier Deep Dive reproductible ;
- faire revoir le résultat par un expert externe ;
- décider des prix ;
- décider si le prochain investissement porte sur le Deep Dive, l'automatisation du
  screening ou l'acquisition commerciale.

## 13. Tableau de décision à maintenir

Mettre à jour ce tableau toutes les deux semaines.

| Question | Mesure | Seuil | État |
| --- | --- | --- | --- |
| Le raccordement est-il un problème prioritaire ? | Entretiens le classant top 3 | >= 70 % | À mesurer |
| Le problème provoque-t-il une perte réelle ? | Sites retardés ou abandonnés | >= 50 % des clients | À mesurer |
| Les clients partagent-ils leurs données ? | Portefeuilles obtenus | >= 5 | À mesurer |
| Paient-ils pour le screening ? | Pilotes payants | >= 2 | À mesurer |
| Le résultat change-t-il une décision ? | Sites reclassés avec justification | >= 30 % | À mesurer |
| Le screening prédit-il la preuve profonde ? | Concordance Deep Dive/PTF | À calibrer | Non disponible |
| Le service est-il reproductible ? | 100 sites en moins de 2 jours | Oui | À tester |
| Le service peut-il être rentable ? | Marge brute après revue humaine | Positive | À mesurer |
| Le besoin est-il récurrent ? | Clients demandant un second run | >= 2 sur 3 | À mesurer |

## 14. Décision recommandée aujourd'hui

**Décision : `go-with-conditions`.**

Conditions :

1. rester concentré sur le BESS français ;
2. vendre d'abord un Portfolio Screening assisté ;
3. corriger les limites de données identifiées ;
4. obtenir des pilotes payants avant une industrialisation SaaS ;
5. construire le Deep Dive avant le Site Finder ;
6. mesurer la précision contre des résultats externes ;
7. ne jamais présenter une reconstruction comme une preuve opérateur.

## 15. Sources principales

### Sources officielles et sectorielles

- [RTE, Bilan électrique 2025 - Production et batteries](https://analysesetdonnees.rte-france.com/bilan-electrique-2025/production)
- [RTE, Bilan électrique 2025 - Prix et flexibilité](https://analysesetdonnees.rte-france.com/bilan-electrique-2025/prix)
- [CRE, délibération 2026-32 sur les raccordements à gabarit](https://www.cre.fr/fileadmin/Documents/Deliberations/2026/260204_2026-32_Procedure_raccordement_RTE.pdf)
- [RTE, procédure de traitement des demandes de raccordement au RPT](https://www.services-rte.com/files/live/sites/services-rte/files/documentsLibrary/Article_1.2.2_Proc%C3%A9dure_de_Traitement_des_demandes_de_raccordement_au_RPT_0888_fr)
- [RTE, conditions générales de PTF indiquant le montant forfaitaire publié](https://www.services-rte.com/files/live/sites/services-rte/files/documentsLibrary/ARTICLE_8.1.1_-_TRAME_TYPE_DE_PTF_PRODUCTEUR_CONDITIONS_GENERALES_ET_PARTICULI%C3%88RES_6015_fr)
- [CRE, TURPE 7 HTB et outils de visualisation](https://www.cre.fr/fileadmin/Documents/Deliberations/2025/250204_2025-39_TURPE_7_HTB.pdf)
- [RTE, cartographie des capacités d'accueil pour le stockage](https://www.services-rte.com/news/le-9-octobre-2025-rte-met-a-jour-la-cartographie-des-capacites-daccuei.html)
- [CRE, retour d'expérience du bac à sable réglementaire 2024](https://www.cre.fr/fileadmin/Documents/Rapports_et_etudes/2025/Rapport_2025-03_REX_Bac_a_sable_2024.pdf)
- [Commission européenne, guidance sur les files de raccordement, décembre 2025](https://energy.ec.europa.eu/document/download/62c46b3d-0df9-42a1-a5fe-c3c71ed5f18c_en?filename=C_2025_8473_1_EN_ACT_part1_v4.pdf)
- [Commission européenne, European Grids Package](https://energy.ec.europa.eu/topics/infrastructure/european-grids_en)
- [JRC, mise en œuvre des recommandations européennes sur le stockage](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC144586/JRC144586_01.pdf)
- [France Renouvelables, stockage et flexibilités](https://www.france-renouvelables.fr/stockage-et-flexibiltes/)
- [SolarPower Europe, EU Battery Storage Market Review 2025](https://www.solarpowereurope.org/insights/outlooks/eu-battery-storage-market-review-2025-1/detail)

### Concurrence et validation de catégorie

- [PVcase, critères de sélection de sites BESS](https://pvcase.com/blog/site-selection-checklist-battery-energy-storage)
- [Glint Solar, développement et screening BESS](https://www.glintsolar.com/resources/everything-you-need-to-know-about-developing-battery-energy-storage-systems-bess)
- [Modo Energy, localisation et risque de raccordement](https://modoenergy.com/research/en/de-germany-bess-where-to-build-a-battery-location-grid-access-capex-redispatch)
- [Gridcog, raccordement flexible et économie BESS](https://www.gridcog.com/blog/top-five-trends-battery-storage-developers-in-germany)
- [DNV, études de faisabilité stockage](https://www.dnv.com/energy/services/energy-storage/feasibility/)

### Forums et retours qualitatifs

- [Reddit r/consulting, retours sur les projets d'interconnexion](https://www.reddit.com/r/consulting/comments/1kkhe6f/how_do_you_help_clients_navigate_grid/)
- [Reddit r/energy, files d'attente et projets spéculatifs](https://www.reddit.com/r/energy/comments/1lumfis/grid_operators_complain_of_too_many_batteries_and/)
- [Reddit r/AskEngineers, obstacles aux projets BESS](https://www.reddit.com/r/AskEngineers/comments/1tfmaws/why_arent_existing_solar_and_wind_plants_racing/)
- [Reddit r/energy, demande pour des logiciels d'analyse d'interconnexion](https://www.reddit.com/r/energy/comments/1enloy5/what_are_some_problems_facing_american_energy/)
