# Carte wayfinder : spec du profiler

Label: wayfinder:map

## Destination

Une spec complète + architecture pour une librairie open source (BSD-3/MIT) de profiling : CLI zéro-instrumentation (`profiler run -- mpirun ./app`) qui orchestre des collecteurs existants, place les kernels sur un roofline model, diagnostique les latences mémoire et réseau, et fait expliquer les bottlenecks par un LLM via pi.dev. La carte est terminée quand la spec peut être remise à une équipe d'implémentation sans décision ouverte.

## Notes

- Tracker : local-markdown (`.scratch/profiler-spec/`), tickets dans `issues/`.
- Skills à consulter : `/grilling` et `/domain-modeling` pour les tickets de décision, `/research` pour les tickets de recherche, `/prototype` pour les prototypes.
- Langue de travail : français.
- Cadrage acté pendant le charting (session du 2026-07-23) :
  - V1 : CPU + GPU + distribué dès le départ.
  - Plateformes v1 : Linux x86/ARM + GPU NVIDIA (CUPTI) et AMD (rocprofiler) + macOS Apple Silicon (M1-M5).
  - Collecte par orchestration de collecteurs existants (LIKWID/perf_events, CUPTI/Nsight, rocprof, PMPI/OTF2) - pas de collecteurs maison.
  - Distribué = MPI uniquement en v1.
  - Langages profilés v1 : compilés (C/C++/Fortran/Rust) via DWARF + Python via un chemin dédié.
  - Moteur d'analyse déterministe (roofline, classification des kernels, détection des bottlenecks calculés par la librairie) ; le LLM explique et suggère, il ne diagnostique pas.
  - Provider LLM : pi.dev (choix ferme).
  - Sortie : résumé terminal + rapport HTML auto-contenu (fonctionne sur cluster sans serveur).
  - Stack : cœur Python ; rapport HTML = mini-app TypeScript compilée, embarquée comme asset statique.
  - Priorité qualité/robustesse/maintenabilité sur coût de développement (préférence utilisateur).

## Decisions so far

<!-- une ligne par ticket résolu : gist + lien -->

## Not yet specified

- Design détaillé du rapport HTML (vues, timeline, interactions) - dépend du modèle de données.
- Packaging et distribution (pip, spack, modules d'environnement, binaire ?) - dépend des dépendances aux collecteurs.
- Stratégie de test et CI sur du hardware hétérogène (CPU variés, GPU des deux vendeurs, cluster MPI, Mac).
- Contenu et structure de la spec finale elle-même (l'assemblage) - graduable quand la majorité des décisions seront prises.
- Gestion des erreurs et dégradation gracieuse quand un collecteur manque sur la machine cible.

## Out of scope

- GPU Intel (Level Zero / VTune), NCCL/RCCL, Dask, torch.distributed, Julia, Windows : reportés post-v1.
- Dashboard web persistant avec historique et comparaison de runs : v2 au plus tôt.
