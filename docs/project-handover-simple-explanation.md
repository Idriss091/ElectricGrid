# Thesegrid - Explication simple pour reprise du projet

## Objectif du projet

Thesegrid est un moteur de pre-faisabilite pour des raccordements flexibles de
batteries BESS au reseau electrique.

La question principale est :

> Si je veux raccorder une batterie de X MW a un point du reseau, est-ce que le
> reseau peut l'accepter, sous quelles limites, avec quel risque de curtailment,
> et est-ce interessant economiquement par rapport a attendre un renforcement ?


Les decisions produites sont :

- `go` : le projet semble acceptable ;
- `go-with-conditions` : le projet peut passer avec une enveloppe flexible ;
- `no-go` : le projet est trop contraint ou trop risque ;
- `resize-recommended` : la puissance demandee est trop elevee, mais une puissance
  plus faible semble acceptable.

## Qu'est-ce qu'un bus ?

Dans un modele de reseau electrique, un `bus` est un noeud electrique.

On peut l'imaginer comme un point ou plusieurs elements se rejoignent :

- une ligne electrique ;
- un transformateur ;
- une charge ;
- une production ;
- une batterie candidate ;
- une barre de poste electrique.

Quand le projet parle de `bus candidat`, cela veut dire :

> un point du reseau ou l'on teste virtuellement le raccordement d'une batterie.

Dans la vraie vie, un bus peut correspondre a une barre dans un poste, un noeud
moyenne tension, ou un point de raccordement simplifie dans le modele.

## Est-ce que les bus actuels sont des endroits en France ?

Non.

Dans l'etat actuel, le projet utilise surtout des reseaux SimBench, par exemple :

```text
1-MV-rural--0-sw
```

SimBench fournit des reseaux electriques benchmark pour faire des experiences
reproductibles. Ces reseaux sont utiles pour tester la methode, mais les bus `2`,
`21`, `24`, etc. ne sont pas des communes francaises ni des postes RTE ou Enedis
identifies.

La bonne interpretation est :

> le projet teste la methode sur un reseau de reference. Si l'on dispose plus tard
> d'un modele de reseau francais reel, la meme logique pourra etre appliquee a de
> vrais points de raccordement.

## Que teste reellement le moteur ?

Le moteur simule virtuellement l'ajout d'une batterie a un bus.

Pour une batterie BESS, il faut tester deux directions :

- `injection` : la batterie decharge et injecte de l'electricite dans le reseau ;
- `withdrawal` ou soutirage : la batterie charge et consomme depuis le reseau.

Le moteur verifie ensuite si le reseau respecte ses contraintes techniques.

Les contraintes testees dans le MVP sont principalement :

- tension trop haute ;
- tension trop basse ;
- ligne trop chargee ;
- transformateur trop charge ;
- calcul de power-flow qui ne converge pas.

Par exemple, si une batterie de 5 MW est ajoutee a un bus et que la tension depasse
la limite de 1.05 pu, le moteur considere que cette puissance cree une violation.

Le MVP ne teste pas encore :

- court-circuit ;
- protections ;
- stabilite dynamique ;
- critere N-1 ;
- harmoniques ;
- regles operateur confidentielles.

## Qu'est-ce qu'un power-flow statique ?

Un power-flow, ou calcul de flux de puissance, repond a la question :

> Pour une situation donnee du reseau, quelles sont les tensions et les flux
> electriques partout dans le reseau ?

`Statique` veut dire que l'on teste une situation fixe, pas toute l'annee heure par
heure.

Le screening rapide fait donc quelque chose comme :

1. ajouter virtuellement une batterie de X MW sur un bus ;
2. lancer un calcul de power-flow ;
3. regarder si les tensions et les chargements restent dans les limites ;
4. repeter pour plusieurs niveaux de puissance et plusieurs bus.

C'est rapide, mais ce n'est qu'un premier filtre, car le reseau change dans le
temps : consommation, production solaire, saison, heure de la journee, etc.

## Capacite ferme

La capacite ferme est la puissance qui semble possible sans restriction
particuliere.

Exemple :

- puissance demandee : 5 MW ;
- le reseau accepte 4 MW sans violation ;
- au-dessus de 4 MW, une tension ou une ligne depasse sa limite.

Dans ce cas, la capacite ferme est environ 4 MW.

Cela signifie :

> dans ce modele simplifie, le raccordement semble possible jusqu'a 4 MW sans
> enveloppe flexible particuliere.

## Capacite conditionnelle

La capacite conditionnelle est la puissance possible si le projet accepte des
restrictions d'exploitation.

Exemple :

- la batterie demande 5 MW ;
- le reseau ne peut pas accepter 5 MW tout le temps ;
- mais il peut accepter 5 MW pendant certaines heures ;
- pendant les heures contraintes, la batterie doit reduire sa puissance.

Dans ce cas, le projet peut etre considere comme acceptable seulement sous
conditions.

Ces conditions sont representees par une enveloppe flexible.

## Enveloppe flexible

Une enveloppe flexible est une regle qui indique combien de MW sont autorises selon
le contexte.

Elle peut dependre de :

- l'heure ;
- la saison ;
- le sens du flux, injection ou soutirage ;
- les contraintes observees sur le reseau.

Exemple simplifie :

```text
00:00 - 07:00 : 5 MW autorises
07:00 - 10:00 : 3 MW autorises
10:00 - 18:00 : injection limitee
18:00 - 21:00 : soutirage limite
21:00 - 24:00 : 5 MW autorises
```

Dans le projet, certaines enveloppes sont inspirees du vocabulaire RTE/CRE, mais
elles ne constituent pas une PTF officielle ni une offre officielle de raccordement.

## Qu'est-ce que le screening teste ?

Le screening teste rapidement plusieurs bus candidats.

Son but est de repondre a :

> Sur quels points du reseau une batterie semble-t-elle la moins risquee ?

Il classe les bus selon :

- capacite ferme ;
- capacite conditionnelle ;
- contraintes reseau observees ;
- curtailment estime ;
- valeur economique proxy ;
- verdict `go`, `go-with-conditions` ou `no-go`.

Le screening est utile pour filtrer les candidats, mais il ne doit pas etre utilise
comme verdict final investisseur.

## Qu'est-ce que le QSTS ?

Le QSTS signifie quasi-static time-series simulation.

Au lieu de tester une seule situation fixe, le moteur rejoue beaucoup d'heures de
l'annee avec des profils de charge et de production.

Pour chaque heure, il demande :

> A cette heure precise, avec cette consommation et cette production, combien de MW
> la batterie peut-elle injecter ou soutirer sans creer de probleme reseau ?

Le QSTS est plus lent que le screening, mais il est plus credible.

Dans le projet, il existe plusieurs niveaux de preuve :

- `qsts_short` : test court, utile comme smoke test ;
- `qsts_stratified` : echantillon d'heures representatives ;
- `qsts_full_year` : validation sur toute l'annee, reference MVP investisseur.

Le full-year QSTS est le niveau le plus fort du MVP, mais il ne remplace toujours pas
une etude officielle.

## Qu'est-ce que le curtailment ?

Le curtailment est la reduction imposee de puissance parce que le reseau ne peut pas
accepter toute l'operation demandee.

Exemple :

- la batterie veut injecter 5 MW ;
- le reseau ne peut accepter que 3 MW a cette heure ;
- il faut reduire de 2 MW.

Le curtailment est donc de 2 MW pour cette heure.

Si cette reduction dure une heure, cela represente 2 MWh d'energie curtaillee.

## Difference entre MW et MWh

`MW` mesure une puissance.

`MWh` mesure une energie sur une duree.

Exemples :

- 2 MW reduits pendant 1 heure = 2 MWh ;
- 2 MW reduits pendant 10 heures = 20 MWh ;
- 5 MW reduits pendant 3 heures = 15 MWh.

Pour une decision investisseur, il faut regarder les deux :

- les MW disent a quel point la limitation est forte a un instant donne ;
- les MWh disent combien d'energie est perdue sur la periode.

## Qu'est-ce que le P90 curtailment MW ?

Le `P90 curtailment MW` est une mesure statistique.

Il signifie :

> Dans 90 % des heures testees, le curtailment est inferieur ou egal a cette
> valeur.

Exemple avec 10 heures :

```text
Curtailment par heure :
0, 0, 0, 0, 0, 1, 1, 2, 3, 5 MW
```

Le P90 est autour de 3 MW.

Cela veut dire :

> 90 % du temps, la reduction necessaire est de 3 MW ou moins.

Autre exemple :

```text
Curtailment par heure :
0, 0, 0, 0, 0, 0, 0, 0, 0, 5 MW
```

Le P90 peut etre 0 MW.

Cela veut dire :

> dans 90 % des heures, il n'y a pas de curtailment.

Mais il reste quand meme une heure avec 5 MW de curtailment.

## Pourquoi le P90 peut etre trompeur

Le P90 ne dit pas tout.

Un site peut avoir :

- un `P90 curtailment MW` tres faible ;
- mais plusieurs episodes rares de curtailment ;
- donc une energie annuelle curtaillee importante en MWh.

C'est une des lecons importantes du projet.

Dans le bundle actuel, le bus 2 semblait acceptable dans les couches rapides, mais la
validation full-year montre que l'energie curtaillee annuelle depasse la tolerance.
Le verdict final devient donc `no-go`.

Conclusion :

> Le P90 MW mesure l'intensite typique du curtailment, mais les MWh mesurent la perte
> totale. Pour une decision investisseur, il faut les deux.

## Lecture du bundle actuel

Le bundle actuel se regenere avec :

```text
docs/demo-pipeline.md
```

Le rapport principal devient `investor_report.html` quand la commande full-year du
pipeline a produit la matrice de validation et le bundle investisseur. Pour un smoke
rapide, lire plutot :

```text
results/demo_pipeline_stratified_smoke/pipeline_report.md
```

La demonstration historique resumait :

- reseau : `1-MV-rural--0-sw` ;
- actif : batterie BESS ;
- puissance demandee : 5 MW ;
- bus evalues : 2, 21, 24 ;
- tolerance P90 : 3 MW ;
- tolerance energie curtaillee : 60 MWh ;
- reference : QSTS full-year.

Le resultat actuel est :

- bus 2 : `no-go` en full-year, malgre un screening favorable ;
- bus 21 : `no-go` ;
- bus 24 : `no-go` a 5 MW ;
- bus 24 : acceptable a 2 MW sous conditions, donc `resize-recommended`.

La conclusion produit est :

> 5 MW n'est pas defendable sur les bus evalues, mais un raccordement reduit a 2 MW
> sur le bus 24 peut etre defendable sous conditions dans ce benchmark.

## Resume en une phrase

Thesegrid teste virtuellement le raccordement d'une batterie sur plusieurs noeuds
d'un reseau benchmark, estime la puissance acceptable sans et avec restrictions,
mesure le curtailment en MW et en MWh, puis transforme ces resultats en decision
investisseur reproductible.
