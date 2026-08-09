# Décision : caractérisation machine (plafonds du roofline)

Type: grilling
Blocked by: 03
Status: resolved

## Question

Comment obtenir les plafonds du roofline (peak FLOPs par précision, bandes passantes par niveau mémoire, bande passante réseau) pour la machine de l'utilisateur ?

Options en présence : microbenchmarks embarqués (à la likwid-bench/ERT/STREAM, exécutés une fois puis mis en cache), base de données de specs constructeur embarquée, valeurs théoriques calculées depuis cpuid/nvidia-smi, ou combinaison. Trancher aussi : où est mis en cache le profil machine, et que faire quand le microbenchmark est impossible (nœud partagé, macOS).

## Answer

Décision prise en session /grilling ; arbitrage complet dans `docs/adr/0002-caracterisation-machine.md`, glossaire enrichi dans `CONTEXT.md` (Plafond, Calibration, Machine).

**Plafonds mesurés, théorique en repli.** Le pic théorique est inatteignable (throttling AVX-512, turbo, cgroups) et ferait basculer le verdict memory-bound / core-bound. La mesure est le chemin nominal ; le calcul théorique produit des plafonds de Qualité « estimé ».

**Noyau de microbenchmark maison embarqué** (triad type STREAM + chaînes de FMA en intrinsics par ISA) comme chemin garanti partout, y compris macOS ; `likwid-bench` orchestré en raffinement optionnel pour les plafonds L1/L2/L3 quand LIKWID est présent. Livraison en wheels précompilées avec dispatch d'ISA à l'exécution, recompilation locale en échappatoire pour les ISA non couvertes (SVE, A64FX, Grace). GPU : PTX embarqué compilé par le driver côté NVIDIA, objets code `gfx` côté AMD, repli sur les pics vendeur étiquetés « estimé ».

**Déclenchement** automatique au premier Run sur une Machine inconnue, avant l'application - seul moment où l'utilisateur détient le nœud de calcul en exclusif. Budget borné à 60 s, plafonds mesurés par ordre de priorité (DRAM + FLOP DP, puis SP, puis caches, puis GPU) ; profil partiel exploitable.

**Identité de la Machine** = empreinte matérielle canonique **combinée à la forme de l'allocation** (cœurs visibles, affinité, cgroup) : réutilisation sur tous les nœuds identiques d'un cluster, mais pas de recyclage du plafond d'un nœud entier par un job partiel. **Cache utilisateur seul** (`$XDG_CACHE_HOME/profiler/machines/`), écriture atomique ; pas de cache site en v1. Le **manifeste du Run embarque l'instantané complet** du profil Machine, donc le Placement roofline reste recalculable ailleurs et plus tard - le cache n'est qu'une optimisation.

**Conditions dégradées** : plafond = maximum des répétitions (c'est une borne supérieure) ; pollution détectée (charge externe, allocation non exclusive, dispersion, écart au théorique) → rétrogradation en « estimé » avec raison, sans quatrième niveau de Qualité. **Concurrence** : plafonds au périmètre de l'allocation + un point mono-thread pour la scalabilité, et le Placement agrège les Mesures au même périmètre avant comparaison. **Réseau** : sonde ping-pong lancée avec le lanceur MPI de l'utilisateur en multi-nœuds, sinon estimé. Cette sonde est le seul composant qui échappe à la livraison précompilée : elle doit être liée à la pile MPI du site, donc construite localement avec le `mpicc` découvert à partir du lanceur observé, puis mise en cache ; sans `mpicc` utilisable, plafond réseau estimé et motif consigné. **Invalidation** par version du noyau de bench ; gouverneur/turbo en métadonnée avec avertissement ; pas de péremption temporelle.

**Repli théorique** : table par microarchitecture (quelques dizaines d'entrées) croisée avec les valeurs lues à l'exécution ; microarchitecture inconnue → « indisponible », jamais d'extrapolation.

Point clarifié au passage : macOS n'est pas un mode dégradé pour la calibration (le noyau maison y mesure de vrais plafonds en NEON) - la dégradation du ticket 02 porte sur le numérateur du roofline, pas sur son dénominateur.
