# 08 - Analyse déterministe

Le moteur d'analyse est une **fonction pure du couple (pivot mesuré, Machine)**. Il ne persiste rien, il est recalculé à la demande, et il est intégralement testable sans matériel.

C'est lui qui produit les « faits » donnés au modèle de langage. Sa reproductibilité est la contrepartie du caractère non reproductible de l'Explication.

## Le Diagnostic

Pour chaque Hotspot au-dessus du plancher statistique :

**Placement roofline** - intensité arithmétique et performance atteinte, comparées aux Plafonds de la Machine sur le même périmètre. Le roofline est l'enveloppe `min(pic de calcul, bande passante × intensité)` : la diagonale mémoire **s'arrête au point de rupture**, elle ne le traverse pas. Cette formule est un invariant testable.

**Classification** - memory-bound, compute-bound, latency-bound, déséquilibre. La classification énonce un régime, pas une cause.

**Déséquilibre entre Loci** - rapport entre le Locus le plus chargé et le moins chargé, calculé à la demande depuis les Mesures et jamais stocké.

## Les deux intensités arithmétiques

Elles ne se substituent jamais l'une à l'autre, et toute mention précise laquelle.

| | Source | Ce qu'elle dit | Disponible |
|---|---|---|---|
| **Intensité DRAM** | Compteurs bruts de trafic mémoire | FLOP par octet réellement échangé avec la mémoire principale, donc sensible à la réutilisation en cache | là où les compteurs existent |
| **Intensité L1** | Analyse statique de boucle | FLOP par octet demandé par le flux d'instructions, insensible à la réutilisation | partout où LLVM sait désassembler |

L'intensité L1 est ce qui rend un roofline possible sur Apple Silicon, où aucun compteur FLOPs n'existe.

## Analyse statique de boucle

Reprend les cas d'usage de CQA/MAQAO **sans dépendre de MAQAO**, en s'appuyant sur le LLVM déjà requis pour la symbolisation. Le travail propre au produit se limite à reconstruire le graphe de flot de contrôle, isoler la boucle interne chaude - la distribution par ligne dit déjà où elle est - et interpréter le résultat.

**Périmètre v1** :

| Résultat | Dépend de |
|---|---|
| taux et largeur de vectorisation | désassembleur seul |
| motif d'accès mémoire (contigu, à pas, indirect) | désassembleur seul |
| intensité arithmétique L1 | désassembleur seul |
| bornes de cycles côté ports d'exécution | modèle d'ordonnancement |
| bornes de cycles côté chaîne de dépendances | modèle d'ordonnancement |

Cette séparation est structurante : **les comptages survivent partout où LLVM sait désassembler**, y compris sur les cœurs Apple dont le modèle d'ordonnancement est approximatif. Seules les bornes de cycles dépendent du modèle.

**Règle de disponibilité**, mécanique et vérifiable puisque LLVM sait lister les `-mcpu` qu'il connaît :

- microarchitecture **absente** de la liste de la version installée : bornes de cycles `indisponible`, avec pour raison « installe un LLVM 19 ou plus récent ». Les comptages restent disponibles ;
- microarchitecture **présente** : bornes `estimé`, avec la raison précisant le modèle utilisé.

**L'analyse statique ne produit jamais `mesuré`** (invariant I6).

Le « gain estimé si la boucle était vectorisée » est **hors périmètre v1** : il suppose de modéliser une transformation, et non de mesurer l'existant.

## Les faits transmis au modèle

L'analyse produit des énoncés déterministes, formulés comme des faits :

- « la boucle ligne 213 n'est pas vectorisée : 98 % des instructions flottantes retirées sont scalaires » ;
- « 41 % des chargements sont des gather » ;
- « 45 % des cycles de ce kernel sont en attente sur `Long Scoreboard` » ;
- « 89 % du plafond mémoire atteint ».

Là où le compteur source n'existe pas, **le fait est `indisponible` et n'est pas transmis** plutôt que d'être transmis approximatif.

## Propagation de la Qualité

Automatique le long du Linéage : la Qualité d'une Métrique dérivée vaut la pire de ses entrées (invariant I4). Des FLOPs estimés donnent une intensité arithmétique estimée, qui donne un placement roofline estimé.

Cette propagation n'est jamais court-circuitée, et c'est ce qui garantit qu'un chiffre affiché `mesuré` dans le rapport l'est de bout en bout.
