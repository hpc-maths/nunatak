# Recherche : inventaire des collecteurs à orchestrer

Type: research
Status: resolved

## Question

Quel collecteur précis orchestrer pour chaque plateforme/métrique de la v1, et sous quelles contraintes (interface, format de sortie, licence, droits) ?

À établir depuis les sources primaires (docs, dépôts, licences) :
- CPU Linux : LIKWID (CLI vs pylikwid, GPL - implications quand on l'exécute vs qu'on le linke) vs perf_events direct (perf CLI, perf.data, paranoid levels) - lequel comme backend principal, lequel en secours ?
- GPU NVIDIA : CUPTI direct vs `ncu`/`nsys` CLI et leurs formats de sortie (sqlite, csv) ; permissions requises (ERR_NVGPUCTRPERM).
- GPU AMD : rocprofiler v1/v2/v3 (l'API a beaucoup bougé) - laquelle est stable, quels formats.
- MPI : interception PMPI maison vs Score-P/OTF2 vs mpiP - lequel donne les latences réseau par rang avec le moins de friction d'installation.
- Python : py-spy, perf avec perf-trampoline (CPython 3.12+), viztracer - quel chemin pour attribuer les échantillons au code Python.
- Pour chaque choix : format de sortie parsable, stabilité de l'interface, licence compatible BSD-3/MIT, besoin de droits root/capabilities.

## Answer

Principe transverse : architecture **"exec + parse", jamais "link"**. Exécuter perf/LIKWID en sous-processus laisse les programmes séparés (FAQ GPL de la FSF) ; lier pylikwid (GPL-2) rendrait l'œuvre combinée GPL - interdit pour un projet BSD-3/MIT.

Recommandations par domaine (principal / secours) :
- **CPU Linux** : perf CLI (`perf stat -j` JSON, `perf script` ; per-process user-space sans privilège même à paranoid=2, CAP_PERFMON pour le reste) / likwid-perfctr (GPL-3, CLI seulement) pour énergie, uncore et métriques dérivées.
- **GPU NVIDIA** : nsys (export sqlite/jsonlines/arrow/parquet, pas de root en mode process-tree) / ncu pour les compteurs par kernel (`--csv`, `.ncu-rep`), avec gestion explicite d'ERR_NVGPUCTRPERM (compteurs réservés admin depuis le pilote 418.43). CUPTI direct écarté en v1 (lib C, couplage ABI, EULA).
- **GPU AMD** : rocprofv3 / rocprofiler-sdk (MIT ; sorties rocpd/SQLite, CSV, JSON, OTF2, pftrace) en principal ; rocprof v1 en secours pour les ROCm anciens. Dépôt migré dans le monorepo ROCm/rocm-systems.
- **MPI** : mpiP (BSD, LD_PRELOAD sans recompilation, temps/volumes par rang et site d'appel) / shim PMPI maison en évolution. Score-P/OTF2 hors chemin par défaut (installation lourde), Caliper rejeté (annotation source requise).
- **Python** : perf + perf-trampoline (CPython 3.12+, `python -X perf`) - seul chemin unifiant piles Python et natives dans un même perf.data / py-spy (MIT, `--native`) pour CPython < 3.12. viztracer écarté (traceur déterministe, autre modèle de données).

Pour la spec : parseurs versionnés par version d'outil détectée, commande "doctor" de diagnostic des permissions, chemin nominal garanti sans root.

Précision apportée par le ticket 10 : côté NVIDIA, `nsys` et `ncu` sont combinés dans **une même exécution**, `ncu` étant borné à quelques lancements par nom de kernel pour contenir le coût du rejeu. Côté macOS, la découverte des Hotspots passe par de l'échantillonnage temporel (`xctrace`, ou `/usr/bin/sample` du système de base quand Xcode est absent), à ajouter à l'inventaire.

Détails sourcés et tableau récapitulatif : `docs/research/collecteurs.md` sur la branche `research/collecteurs` (commit 73bf896).
