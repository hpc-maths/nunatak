# 14 - Feuille de route et angles morts

## Angles morts connus

**L'équivalent macOS des jeux d'événements par microarchitecture.** LIKWID fournit ailleurs des jeux d'événements et des groupes de métriques validés par microarchitecture ; rien d'équivalent n'existe sur Apple Silicon. Les `.plist` de `/usr/share/kpep` sont la matière première identifiée, mais aucune décision n'a été prise. Portée réelle limitée : le chemin macOS nominal est l'échantillonnage temporel sans compteurs ([macOS](../guide/macos/index.md)), et le volet plafonds est couvert par le noyau de calibration ([Machine et plafonds](../guide/machine/index.md)). Cet angle mort ne bloque donc que le backend kperf expert.

**Les cibles génériques ROCm** ([chapitre 12](12-packaging.md)) sont à évaluer : elles réduiraient l'énumération des cibles `gfx`.

## Ce que la v2 pourrait apporter

Ces pistes ont été identifiées en chemin et écartées de la v1 sans que l'architecture ne les empêche :

- **historique et comparaison de plus de deux Runs.** Le socle existe déjà : identité logique stable, Provenance complète, [`compare`](../guide/compare/index.md) fonctionnel ;
- **éclatement d'un Hotspot par contexte d'appel.** Les piles sont persistées, il suffirait de les exploiter ([Call stacks](../guide/stacks/index.md)) ;
- **cubins précompilés côté NVIDIA** si le délai de compilation PTX au premier lancement se révèle gênant ([chapitre 12](12-packaging.md)) ;
- **« gain estimé si la boucle était vectorisée »**, qui suppose de modéliser une transformation plutôt que de mesurer l'existant ;
- **plateformes reportées** : GPU Intel, NCCL/RCCL, Dask, `torch.distributed`, Julia, Windows.

## Critère de fin

La spec est tenue si un développeur peut lancer nunatak sur son application sans la modifier, et obtenir un rapport qui lui dit où part son temps, contre quel plafond il bute, **et dans quelle mesure il peut croire ce qu'il lit**.

Ce dernier point n'est pas un ornement : c'est ce qui distingue ce produit, et c'est ce que le site rend mécanique : [comment lire ce que nunatak dit](../guide/reading-what-nunatak-tells-you.md).
