# Spécification de nunatak

nunatak est un profileur zéro-instrumentation pour le calcul haute performance. Il orchestre des collecteurs existants, place les unités de calcul sur un roofline, diagnostique les goulots d'étranglement CPU, GPU, mémoire et réseau, et fait expliquer les résultats par un modèle de langage.

Ce document est **normatif** : il dit ce qu'il faut construire. Il ne dit pas pourquoi. Chaque chapitre renvoie aux décisions de `docs/development/decisions/`, qui portent le raisonnement, les options écartées et leurs raisons. Un désaccord sur une décision se règle en relisant l'ADR, pas en réinterprétant la spec.

**Ce qui est construit et documenté n'est plus ici.** Chaque chapitre est retiré au fur et à mesure que le site en hérite, et ce qui reste est donc le travail non construit - une feuille de route interne, que le site ne publie pas et ne promet pas. Le produit se lit sur [le site](../index.md).

## Comment lire

Le vocabulaire est contraignant et vit sur le site : [glossaire](../reference/glossary.md), relations entre entités comprises. Ce qui suit se lit par chantier, et chaque chantier est du travail à faire.

## Chapitres

| | Chapitre | Ce qu'il reste à construire |
|---|---|---|
| 05 | [Collecte](05-collecte.md) | collecte GPU, LIKWID, shim PMPI, fréquence adaptative, kperf |
| 06 | [Attribution](06-attribution.md) | attribution GPU, rapports d'optimisation |
| 07 | [Machine et plafonds](07-machine-et-plafonds.md) | noyau précompilé et dispatch d'ISA, `likwid-bench` |
| 10 | [Rapport](10-rapport.md) | le tiroir assembleur |
| 12 | [Packaging et distribution](12-packaging.md) | canaux de distribution, cibles GPU |
| 14 | [Feuille de route et angles morts](14-feuille-de-route.md) | les angles morts et les pistes v2 |

## Correspondance avec les ADR

| ADR | Sujet | Chapitres |
|---|---|---|
| [0001](../development/decisions/0001-pivot-data-model.md) | Modèle de données pivot | - |
| [0002](../development/decisions/0002-machine-characterisation.md) | Caractérisation machine | 07 |
| [0003](../development/decisions/0003-profiling-modes.md) | Modes de profiling et budget d'overhead | 05 |
| [0004](../development/decisions/0004-source-attribution.md) | Attribution vers le source | 06 |
| [0005](../development/decisions/0005-packaging-and-distribution.md) | Packaging et distribution | 12 |
| [0006](../development/decisions/0006-html-report-design.md) | Design du rapport HTML | 10 |
| [0007](../development/decisions/0007-cli-surface.md) | Surface CLI | - |
| [0008](../development/decisions/0008-test-and-ci-strategy.md) | Stratégie de test et CI | - |

## État

Les 16 tickets de conception sont résolus et les 8 ADR sont écrits : aucune décision de conception ne reste ouverte. Les chapitres 01, 02, 08 et 11 ont été retirés, leur contenu étant construit et documenté sur le site. Ce qui reste - collecte et attribution GPU, canaux de distribution, cibles matérielles, quelques raffinements de mesure, et la feuille de route du chapitre 14 - est du travail non construit, que le site ne publie pas.
