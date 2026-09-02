# 12 - Packaging et distribution

Référence : [ADR 0005](../development/decisions/0005-packaging-and-distribution.md).

Ce qui est construit et documenté a rejoint le site : le plancher LLVM
et ce que chaque outil manquant coûte sont dans [Installing nunatak for
a team](../deployment/installing.md) et [Static loop
analysis](../guide/static-loop-analysis.md) ; le contenu de la wheel, le
hook qui compile le rapport et les deux Python sans rapport l'un avec
l'autre dans [Install nunatak](../getting-started/installing.md) ; la
sonde réseau et mpiP construits au premier usage puis mis en cache par
pile MPI dans [le stack MPI du site](../deployment/mpi-stack.md) et
[Machine et plafonds](../guide/machine/index.md) ; la politique de
détection des outils fournis par le site dans [le catalogue des
dégradations](../reference/degradations.md). La politique de versions de
Python, la veille LLVM et le choix « exec + parse jamais lié » sont dans
l'ADR 0005.

## Reste à construire

- **Les canaux de distribution.** conda-forge et spack livrant un
  produit complet - LLVM, Node.js, pi et py-spy en dépendances
  déclarées - et PyPI livrant le cœur en déclarant ce qui manque, un
  seul comportement pour deux niveaux de complétude. Rien n'est publié
  aujourd'hui.
- **La réserve à écrire dans la recette spack** : sans LLVM externe
  déclaré dans `packages.yaml`, `spack install nunatak` compile LLVM
  depuis les sources, ce qui prend des heures. `doctor` doit savoir dire
  « ton LLVM système ferait l'affaire, déclare-le en externe ».
- **Cibles matérielles GPU** : PTX seul côté NVIDIA, le pilote
  compilant à la volée pour l'architecture présente ; `gfx90a` (MI200),
  `gfx942` (MI300) et `gfx908` (MI100) côté AMD, où une cible non
  listée ne tourne pas du tout. Les cibles génériques par famille
  introduites par ROCm sont à évaluer : elles réduiraient cette
  énumération.
