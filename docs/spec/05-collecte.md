# 05 - Collecte

Référence : [ADR 0003](../development/decisions/0003-profiling-modes.md), [ADR 0005](../development/decisions/0005-packaging-and-distribution.md).

## Le cadre imposé

Le comptage par région exige des marqueurs dans le source : il est hors jeu pour un outil zéro-instrumentation. Attribuer des Compteurs bruts à un Hotspot sans toucher au code n'a donc qu'une voie, **l'échantillonnage déclenché par événement**. Tout ce chapitre se pose dans ce cadre.

## Une exécution par défaut

`nunatak run` **exécute l'application une seule fois**. Les groupes d'événements qui ne tiennent pas dans les compteurs du PMU sont multiplexés par le noyau.

Un **mode multi-passes explicite** relance l'application avec des groupes disjoints pour qui veut des compteurs exacts. Il n'est jamais activé d'office : relancer une application dans une allocation que l'utilisateur paie n'est pas une décision que l'outil prend seul.

En mode multi-passes, un **groupe témoin** (cycles et instructions retirées) est répliqué dans chaque Passe et comparé à la fin. Un écart au-delà du seuil signe une application non reproductible - critère de convergence, ordonnancement dynamique, MPI non déterministe - et les Mesures fusionnées sont rétrogradées en `estimé` avec la raison.

Une invocation reste **un seul Run** quel que soit le nombre de Passes, et chaque Mesure garde la trace de sa Passe d'origine.

## Budget d'overhead

**10 % du temps mural, tenu par construction et jamais vérifié après coup** : le mesurer exigerait une exécution de référence non profilée, ce qui doublerait le coût de l'utilisateur.

Les seuls leviers sont la fréquence d'échantillonnage, le nombre de lancements GPU instrumentés et la taille des tampons. La fréquence est **adaptative** à la durée et au débit observés : une fréquence fixe produit trop peu d'échantillons sur une application de trois secondes et des dizaines de millions d'échantillons inutiles sur une application de six heures.

**Ordre de sacrifice, fixe et documenté**, quand budget, compteurs disponibles et durée entrent en conflit :

1. temps par Hotspot et agrégats par rang ;
2. trafic mémoire (qui tranche memory-bound) ;
3. FLOPs par précision (qui complète le roofline) ;
4. niveaux de cache, détail par kernel GPU, assembleur.

Sans cet ordre, c'est la configuration du collecteur qui déciderait en silence de ce que l'utilisateur perd.

## Plancher statistique

Chaque Mesure porte son **nombre d'échantillons et son erreur relative**, décroissante en `1/racine(n)`.

- sous un plancher, la Mesure passe `estimé` ;
- bien en dessous, le Hotspot rejoint un agrégat **« autres »** qui préserve les totaux sans polluer les vues ;
- **le modèle ne reçoit jamais un Hotspot sous le plancher.**

## Collecteurs par plateforme

| Domaine | Principal | Secours |
|---|---|---|
| CPU Linux | `perf` (JSON, `perf script`) | `likwid-perfctr` pour énergie, uncore, métriques dérivées |
| GPU NVIDIA | `nsys` sur toute la timeline | `ncu` borné en lancements pour les compteurs par kernel |
| GPU AMD | `rocprofv3` | `rocprof` v1 pour les ROCm anciens |
| MPI | `mpiP` (`LD_PRELOAD`) | shim PMPI maison |
| Python | `perf` + trampolines CPython 3.12+ | py-spy |
| macOS | `xctrace` si Xcode | `/usr/bin/sample`, plus `powermetrics` pour les agrégats |

**GPU en une seule exécution** : `nsys` couvre toute la timeline à faible overhead, `ncu` n'instrumente que quelques lancements par nom de kernel, le premier (warm-up, non représentatif) étant exclu. Le rejeu de kernel, qui coûte de 10 à 100 fois, ne s'applique donc qu'à une poignée de lancements. Le roofline GPU est disponible par défaut, sur un échantillon dont **la couverture est annoncée dans le rapport**.

**Un compteur multiplexé reste `mesuré`** tant que sa couverture `time_running / time_enabled` dépasse le seuil (de l'ordre de 80 %, configurable) ; en dessous il est rétrogradé. Étiqueter `estimé` tout ce qui est multiplexé rendrait le rapport uniformément gris et priverait l'étiquette de son pouvoir discriminant.

## macOS

Pas d'échantillonnage déclenché par événement. Le mode nominal est l'échantillonnage **temporel** - `xctrace` et son Time Profiler si Xcode est présent, `/usr/bin/sample` sinon - complété par `powermetrics` pour les agrégats par processus. Les Compteurs bruts par Hotspot y sont `indisponible` et le roofline reste estimé, l'intensité arithmétique L1 étant fournie par l'analyse statique (chapitre 08).

kperf demeure un backend expert, opt-in, jamais automatique.
