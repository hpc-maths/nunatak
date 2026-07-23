# Recherche : état de l'art du roofline automatique

Type: research
Status: claimed

## Question

Comment les outils de référence construisent-ils un roofline et y placent-ils les kernels, et quel est le jeu minimal de métriques par plateforme ?

À établir depuis les sources primaires (docs et publications de LIKWID, MAQAO, Intel Advisor, NVIDIA Nsight Compute, papiers roofline d'origine - Williams et al., ERT) :
- Comment chaque outil mesure l'intensité arithmétique (FLOPs comptés vs échantillonnés, trafic mémoire DRAM vs caches) et les plafonds (peak FLOPs, bandes passantes par niveau).
- Roofline hiérarchique (L1/L2/L3/DRAM) : qui le fait et comment.
- Côté GPU : quelles métriques CUPTI/rocprof suffisent pour un roofline correct.
- Les pièges connus (compteurs FLOP absents sur certaines microarchitectures, multiplexing, overcounting).
- Ce que MAQAO fait au-delà du roofline (analyse statique du binaire, qualité de vectorisation) qui inspirerait notre moteur de diagnostic.
