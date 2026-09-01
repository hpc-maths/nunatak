# 12 - Packaging et distribution

Référence : [ADR 0005](../development/decisions/0005-packaging-and-distribution.md).

## Le principe organisateur

> **conda-forge et spack livrent un produit complet** : ils tirent LLVM, Node.js, pi et py-spy en dépendances déclarées.
> **PyPI livre le cœur** et déclare ce qui manque, `doctor` donnant la commande exacte pour compléter.

Un seul comportement, deux niveaux de complétude, aucune divergence de code entre canaux.

Ce que ça coûte, et il faut le dire : un utilisateur pip sans LLVM obtient un outil **partiellement fonctionnel dès la première installation**. Ce n'est acceptable que parce que `doctor` le dit franchement, avant le run, avec la commande exacte.

## Trois catégories d'outils externes

| Catégorie | Contenu | Politique |
|---|---|---|
| **Livrés par nos canaux** | py-spy, Node.js, pi, LLVM | dépendances déclarées |
| **Construits localement** | sonde réseau, mpiP | sources embarquées, construction au premier usage |
| **Fournis par le site** | `nsys`, `ncu`, `perf`, rocprofv3, LIKWID | **jamais redistribuables** |

Pour la troisième catégorie, la seule politique tenable est **détecter, nommer la capacité perdue, indiquer comment le site la fournit** (« `module load cuda` puis relance »). Aucune installation guidée qui téléchargerait quoi que ce soit : l'EULA NVIDIA l'interdit pour `nsys` et `ncu`, et télécharger des outils sur une machine partagée n'est de toute façon pas notre rôle.

## LLVM

**Dépendance externe, jamais vendorisée.** `llvm@19:`.

Le seuil 19 vient d'une mesure sur les tables de microarchitectures : LLVM 17 apporte znver4, sapphirerapids, graniterapids, apple-m1/m2 et neoverse-n1/n2/v1/v2 ; **18** ajoute apple-m3 ; **19** ajoute **znver5, apple-m4, neoverse-v3 et n3** ; **20** ajoute diamondrapids. Un plancher plus bas dégraderait l'outil précisément sur le matériel neuf, celui dont personne n'a l'habitude.

- **17 et 18 sont tolérés, pas refusés** : la symbolisation y est complète, seule l'analyse de boucle se restreint aux microarchitectures connues de cette version.
- En dessous de 17, ou sans LLVM : **repli sur le sous-processus système** (chapitre 06), et pas d'analyse de boucle.
- La sûreté est **mécanique** : microarchitecture absente de la liste des `-mcpu` de la version installée, les bornes de cycles sont `indisponible`. Sur un nœud Zen 5 avec LLVM 18, aucun résultat faux n'est produit, seulement un manque déclaré.
- La variation entre sites est acceptée **parce qu'elle est enregistrée** : version de LLVM et `-mcpu` retenu vont dans la Provenance.

**Réserve à documenter dans la recette spack** : sans LLVM externe déclaré dans `packages.yaml`, `spack install nunatak` compilera LLVM depuis les sources, ce qui prend des heures. `doctor` doit savoir dire « ton LLVM système ferait l'affaire, déclare-le en externe ».

## Ce que contient la wheel

**Le noyau de calibration et la sonde réseau sont des exécutables autonomes**, invoqués en sous-processus, pas des modules d'extension Python. Trois raisons :

1. c'est le principe « exec + parse » appliqué à nos propres binaires ;
2. la wheel devient `py3-none-<plateforme>`, donc **un artefact par plateforme et non par couple (plateforme, version de Python)** ;
3. la Calibration mesurée dans un processus propre donne une borne plus juste.

**Versions de Python : le support amont de CPython**, sans politique maison. Une version est abandonnée le jour où CPython l'abandonne.

À écrire dans la documentation, la confusion étant garantie : **la version de Python qui exécute nunatak n'a rien à voir avec celle de l'application profilée**. Le seuil de 3.12 du chapitre 06 porte sur l'interpréteur de l'application.

## Cibles matérielles

**NVIDIA : PTX seul**, pour une base basse. Le pilote compile le PTX à la volée pour l'architecture réellement présente, ce qui couvre gratuitement les GPU postérieurs à la publication de la wheel.

**AMD : `gfx90a` (MI200, Frontier et LUMI), `gfx942` (MI300, El Capitan), `gfx908` (MI100).** Il n'existe pas d'équivalent du PTX : une cible non listée ne tourne pas du tout. Le reste passe par la recompilation locale. Les **cibles génériques par famille** récemment introduites par ROCm sont à évaluer à l'implémentation, elles réduiraient cette énumération.

Cette asymétrie NVIDIA/AMD est **documentée comme un choix, pas subie comme un oubli**, au même titre que l'attribution par ligne indisponible sur AMD (chapitre 06).

**CPU : dispatch d'ISA à l'exécution** (`CPUID`, `AT_HWCAP`). Nécessaire et non cosmétique (chapitre 07).

## La sonde réseau

Elle se lie à la pile MPI du site, dont les ABI (OpenMPI, MPICH, Intel MPI, Cray MPICH) sont mutuellement incompatibles. MPI 5.0, approuvé le 5 juin 2025, normalise un ABI : **à surveiller, pas à parier dessus**, les implémentations puis les centres mettant des années à suivre.

- construite **au premier usage, jamais à l'installation** : sur un cluster à modules, le MPI chargé à l'installation n'est presque jamais celui du job, et l'erreur ne se manifesterait qu'à l'exécution, sous forme de symboles manquants ou, pire, de mesures fausses ;
- mise en cache par clé `(implémentation, version, mpicc)` ;
- construite de préférence pendant `doctor`, donc sur un nœud de connexion, certains nœuds de calcul n'ayant pas de compilateur ;
- **la pile MPI est enregistrée dans la Provenance** : une analyse réseau dont on ignore la pile sous-jacente n'est pas interprétable ;
- pas de `mpicc` utilisable : analyse MPI `indisponible`, dégradation nommée.

**Le mécanisme couvre aussi mpiP** : le `LD_PRELOAD` évite de recompiler l'application, pas de compiler mpiP.

## Veille de version

LLVM publie une majeure **tous les six mois à date prévisible**. La veille se planifie donc au lieu de se subir, et elle doit être **outillée et non déclarative**.

- un **job de CI sur chaque rc et chaque majeure** qui diffe la liste des `-mcpu` contre la version précédente et ouvre un ticket listant les microarchitectures nouvellement connues, puis rejoue le corpus de non-régression ;
- **borne supérieure ouverte, fenêtre testée déclarée** : au-delà, `doctor` **avertit sans refuser**. Refuser condamnerait l'utilisateur d'un conda-forge à jour à attendre notre release, pour un risque le plus souvent inexistant ;
- la même veille couvre **tous les outils orchestrés** ;
- **cadence de release propre**, non alignée sur celle de LLVM.
