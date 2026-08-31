# 01 - Vision et périmètre

## Ce que le produit fait

Un développeur lance son application sous nunatak sans modifier une ligne de code :

```
nunatak run -- mpirun -n 256 ./solveur
```

Il obtient un répertoire de Run contenant les mesures, un résumé dans son terminal, et un rapport HTML auto-contenu qui lui dit **où part son temps, contre quel plafond il bute, et pourquoi**.

Le produit se distingue sur trois points.

**Zéro instrumentation.** Aucun marqueur à insérer, aucune recompilation exigée. C'est ce qui écarte d'emblée les outils à annotation de source, et c'est une contrainte structurante : elle interdit le comptage par région et impose l'échantillonnage déclenché par événement (chapitre 05).

**Un roofline utilisable sans être expert.** Les plafonds de la machine sont mesurés, pas lus dans une fiche technique. Les kernels y sont placés automatiquement, et l'écart au plafond est traduit en un verdict lisible.

**Un diagnostic déterministe, une explication générée.** Le moteur d'analyse calcule les faits ; le modèle de langage les explique et suggère. Cette frontière est absolue et se retrouve dans chaque chapitre : **le modèle ne diagnostique jamais**.

## Ce que le produit n'est pas

- **Ce n'est pas un traceur.** Il ne produit pas une trace exhaustive de tous les événements d'exécution. Le flux d'Événements existe (lancements GPU, appels MPI) mais il alimente la timeline et l'analyse réseau, pas une reconstruction complète.
- **Ce n'est pas un débogueur de correction.** Il mesure la performance, pas la justesse.
- **Ce n'est pas un tableau de bord.** Il n'y a ni serveur, ni base de données, ni historique persistant. Un Run est un répertoire (chapitre 11).
- **Ce n'est pas un remplaçant d'Instruments sur macOS.** Le chemin macOS sert la boucle de développement courte, pas le verdict de référence (chapitre 06).

## Périmètre de la v1

**Plateformes**

| | Couverture v1 |
|---|---|
| CPU | Linux x86-64 (Intel, AMD) et aarch64 |
| GPU | NVIDIA et AMD |
| Portable | macOS Apple Silicon, en mode dégradé assumé |
| Distribué | MPI uniquement |

**Langages profilés** : compilés (C, C++, Fortran, Rust) par le chemin DWARF, et Python par un chemin dédié.

**Licence** : BSD-3 ou MIT. Cette contrainte est structurante et non cosmétique : elle impose que tout composant sous GPL soit **exécuté en sous-processus et jamais lié** ([architecture](../development/architecture.md)), et elle conditionne ce que la distribution peut embarquer (chapitre 12).

## Hors périmètre v1

Reporté, sans que rien dans l'architecture ne l'empêche :

- GPU Intel (Level Zero, VTune) ;
- NCCL et RCCL, Dask, `torch.distributed`, Julia ;
- Windows ;
- tableau de bord web persistant avec historique et comparaison de plusieurs Runs. Seul un diff ponctuel entre **deux** Runs entre en v1 (chapitre 11).

## L'utilisateur visé

Un développeur d'application scientifique qui sait lire un profil mais n'est pas expert en microarchitecture. Il travaille sur son portable et exécute sur un cluster. Il a un temps de calcul limité et payé, ce qui a deux conséquences directes :

- **on ne relance jamais son application d'autorité** (chapitre 05) ;
- **on lui dit ce qui manquera avant de consommer son allocation, pas après** (chapitre 11).

## Priorités de conception

Dans cet ordre, et en cas de conflit c'est cet ordre qui tranche :

1. **Honnêteté** - ne jamais présenter comme sûr ce qui ne l'est pas. Le chapitre 03 en fait un mécanisme.
2. **Robustesse** - fonctionner en mode dégradé plutôt que refuser.
3. **Maintenabilité** - le produit doit survivre à dix ans d'évolution des outils qu'il orchestre.
4. **Simplicité d'usage** - une commande, pas une méthodologie.

Le coût de développement n'est pas un critère d'arbitrage.
