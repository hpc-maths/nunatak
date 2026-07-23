# Recherche : état de l'art du roofline automatique

Type: research
Status: resolved

## Question

Comment les outils de référence construisent-ils un roofline et y placent-ils les kernels, et quel est le jeu minimal de métriques par plateforme ?

À établir depuis les sources primaires (docs et publications de LIKWID, MAQAO, Intel Advisor, NVIDIA Nsight Compute, papiers roofline d'origine - Williams et al., ERT) :
- Comment chaque outil mesure l'intensité arithmétique (FLOPs comptés vs échantillonnés, trafic mémoire DRAM vs caches) et les plafonds (peak FLOPs, bandes passantes par niveau).
- Roofline hiérarchique (L1/L2/L3/DRAM) : qui le fait et comment.
- Côté GPU : quelles métriques CUPTI/rocprof suffisent pour un roofline correct.
- Les pièges connus (compteurs FLOP absents sur certaines microarchitectures, multiplexing, overcounting).
- Ce que MAQAO fait au-delà du roofline (analyse statique du binaire, qualité de vectorisation) qui inspirerait notre moteur de diagnostic.

## Answer

- **Définition de référence** (Williams et al.) : intensité opérationnelle sur le trafic DRAM (après filtrage des caches) ; ceilings ordonnés du moins au plus coûteux à atteindre - une grammaire réutilisable telle quelle par notre moteur de diagnostic.
- **Plafonds** : tous les outils matures les mesurent empiriquement sur la machine cible (ERT, likwid-bench, benchmarks d'Advisor, microbenchmarks rocprofiler-compute) ; seul Nsight Compute les dérive de métriques `.peak_sustained`. Signal fort pour le ticket 05 : microbenchmarks embarqués.
- **Trois stratégies de mesure de l'intensité arithmétique** : compteurs matériels bruts (LIKWID : `FP_ARITH_INST_RETIRED.*` pondérés 1/2/4/8 + `CAS_COUNT*64` uncore), instrumentation binaire + simulation de cache (Advisor CARM, 4 points L1->DRAM par boucle), compteurs SASS exacts avec kernel replay (Nsight Compute).
- **Jeu minimal GPU validé** (méthodologie NERSC/NVIDIA) : `sm__cycles_elapsed` + 9 compteurs `sass_thread_inst_executed_op_*_pred_on.sum` (FLOPs = add + mul + 2*fma) + `dram__bytes.sum` ; hiérarchie via `lts__t_bytes`/`l1tex__t_bytes`. AMD : `SQ_INSTS_VALU_*` (x64 lanes, x2 FMA, MFMA à part) + `TCC_EA_*`.
- **Pièges sourcés** : Haswell sans compteurs FLOP, Sandy Bridge non fiables, E-cores Gracemont sans aucun événement FLOP, Zen 2/3 sans distinction SP/DP (+ événement MERGE), masques AVX-512 comptés pleine largeur, FMA compte double, uncore par socket seulement. Le modèle de données doit porter une notion de fiabilité/disponibilité par métrique et par microarchitecture.
- **MAQAO/CQA** : la brique au-delà du roofline - borne statique de cycles L1-résident par boucle, ratio de vectorisation, dépendances/DIV-SQRT/spill ; l'écart borne statique vs mesure tranche core-bound vs memory-bound de façon déterministe. Candidat sérieux pour enrichir le moteur de diagnostic et le contexte donné au LLM.

Détails sourcés : `docs/research/roofline-etat-art.md` sur la branche `research/roofline-etat-art` (commit 99b9b50).
