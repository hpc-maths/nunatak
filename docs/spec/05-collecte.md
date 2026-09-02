# 05 - Collecte

Référence : [ADR 0003](../development/decisions/0003-profiling-modes.md), [ADR 0005](../development/decisions/0005-packaging-and-distribution.md).

Ce qui est construit et documenté a rejoint le site : l'exécution unique
par défaut et le mode multi-passes avec son groupe témoin sont dans
[Multi-pass runs](../guide/multi-pass/index.md) ; le multiplexage et la
couverture d'un compteur dans
[Counter groups](../guide/counter-groups.md) ; le plancher statistique
dans [comment lire ce que nunatak
dit](../guide/reading-what-nunatak-tells-you.md) ; les collecteurs CPU,
Python, MPI et macOS dans [Python](../guide/python/index.md),
[MPI runs](../guide/mpi/index.md), [macOS](../guide/macos/index.md) et
[ce qu'une machine doit fournir](../deployment/installing.md). Le cadre
imposé - pas de comptage par région sans marqueurs, donc de
l'échantillonnage - et le budget d'overhead sont dans l'ADR 0003.

## Reste à construire

- **Collecte GPU en une seule exécution** : `nsys` sur toute la
  timeline, `ncu` borné à quelques lancements par nom de kernel - le
  premier, non représentatif, exclu - et la couverture de cet
  échantillon annoncée dans le rapport. `rocprofv3` côté AMD,
  `rocprof` v1 pour les ROCm anciens.
- **LIKWID en secours du chemin CPU** : énergie, uncore, métriques
  dérivées par microarchitecture. Jamais en dépendance.
- **Shim PMPI maison** en secours de mpiP, dont le `LD_PRELOAD` est
  aujourd'hui la seule voie.
- **Fréquence d'échantillonnage adaptative** à la durée et au débit
  observés, avec l'ordre de sacrifice qui la borne : temps par Hotspot
  et agrégats par rang, puis trafic mémoire, puis FLOPs par précision,
  puis niveaux de cache, détail par kernel GPU et assembleur. La
  fréquence est fixe aujourd'hui, et le budget de 10 % du temps mural
  n'est pas tenu sur un noyau riche en flottants.
- **kperf** sur macOS, backend expert, opt-in, jamais automatique.
