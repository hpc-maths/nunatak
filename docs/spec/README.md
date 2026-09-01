# Spécification de nunatak

nunatak est un profileur zéro-instrumentation pour le calcul haute performance. Il orchestre des collecteurs existants, place les unités de calcul sur un roofline, diagnostique les goulots d'étranglement CPU, GPU, mémoire et réseau, et fait expliquer les résultats par un modèle de langage.

Ce document est **normatif** : il dit ce qu'il faut construire. Il ne dit pas pourquoi. Chaque chapitre renvoie aux décisions de `docs/development/decisions/`, qui portent le raisonnement, les options écartées et leurs raisons. Un désaccord sur une décision se règle en relisant l'ADR, pas en réinterprétant la spec.

## Comment lire

Deux chapitres sont à lire par tout le monde, dans l'ordre, avant le reste :

1. [Vision et périmètre](01-vision-et-perimetre.md) - ce qu'est le produit, et surtout ce qu'il n'est pas.
2. [Modèle de domaine](02-modele-de-domaine.md) - le vocabulaire. Il est contraignant : les mêmes mots dans le code, l'interface et la documentation.

Le reste se lit par chantier.

## Chapitres

| | Chapitre | Chantier |
|---|---|---|
| 01 | [Vision et périmètre](01-vision-et-perimetre.md) | tous |
| 02 | [Modèle de domaine](02-modele-de-domaine.md) | tous |
| 05 | [Collecte](05-collecte.md) | orchestration des collecteurs |
| 06 | [Attribution](06-attribution.md) | symbolisation, DWARF, Python, GPU |
| 07 | [Machine et plafonds](07-machine-et-plafonds.md) | calibration |
| 08 | [Analyse déterministe](08-analyse.md) | moteur d'analyse |
| 09 | [Explication](09-explication.md) | couche LLM |
| 10 | [Rapport](10-rapport.md) | mini-app TypeScript |
| 11 | [Interface en ligne de commande](11-cli.md) | CLI, configuration |
| 12 | [Packaging et distribution](12-packaging.md) | build, wheels, canaux |
| 14 | [Feuille de route et angles morts](14-feuille-de-route.md) | pilotage |

## Correspondance avec les ADR

| ADR | Sujet | Chapitres |
|---|---|---|
| [0001](../development/decisions/0001-pivot-data-model.md) | Modèle de données pivot | 02 |
| [0002](../development/decisions/0002-machine-characterisation.md) | Caractérisation machine | 07 |
| [0003](../development/decisions/0003-profiling-modes.md) | Modes de profiling et budget d'overhead | 05 |
| [0004](../development/decisions/0004-source-attribution.md) | Attribution vers le source | 06 |
| [0005](../development/decisions/0005-packaging-and-distribution.md) | Packaging et distribution | 12 |
| [0006](../development/decisions/0006-html-report-design.md) | Design du rapport HTML | 10 |
| [0007](../development/decisions/0007-cli-surface.md) | Surface CLI | 11 |
| [0008](../development/decisions/0008-test-and-ci-strategy.md) | Stratégie de test et CI | - |

Le glossaire de référence est [`docs/reference/glossary.md`](../reference/glossary.md). Le chapitre 02 en donne les relations et les invariants ; il ne le remplace pas.

## État

Les 16 tickets de conception sont résolus et les 8 ADR sont écrits. Cette spec est **complète au sens où elle ne laisse aucune décision de conception ouverte**. Elle laisse en revanche des choix d'implémentation ouverts, qui sont signalés comme tels au fil du texte, et un angle mort connu, décrit au chapitre 14.
