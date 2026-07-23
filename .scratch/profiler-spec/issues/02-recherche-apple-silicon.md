# Recherche : collecte de métriques sur Apple Silicon (M1-M5)

Type: research
Status: resolved

## Question

Que peut-on réellement collecter sur macOS Apple Silicon pour alimenter un roofline et des diagnostics mémoire, sans instrumentation du code ?

À établir depuis les sources primaires (docs Apple, man pages, projets open source) :
- Compteurs CPU : kperf/kpc (framework privé ?), `xctrace` et ses exports, `powermetrics` - qu'est-ce qui est utilisable par un outil tiers redistribuable, avec quelles permissions (sudo, entitlements) ?
- Compteurs GPU (Metal) : que expose Metal System Trace / MTLCounterSampleBuffer pour un binaire qu'on ne contrôle pas ?
- Quelles métriques roofline (FLOPs, bande passante mémoire) sont atteignables, et lesquelles sont impossibles ?
- Comment des projets existants font (asitop, macpm, Instruments) et ce que ça implique pour notre orchestration.

## Answer

macOS Apple Silicon est nettement plus contraint que Linux ; la v1 y sera un mode dégradé et étiqueté comme tel.

- **kperf/kpc** : API privée (PrivateFrameworks), root obligatoire (gate `ktrace_read_check()` dans XNU ; l'entitlement ktrace-allow ne marche que sur noyaux DEBUG), et client PMU exclusif (conflit EACCES avec Instruments). Utilisable mais fragile : backend isolé, optionnel, jamais sur le chemin nominal.
- **Événements PMU** : documentés publiquement dans `/usr/share/kpep/*.plist` (M1 : 67 événements, M5 : 135) et l'Apple Silicon CPU Optimization Guide. **Aucun compteur de FLOPs** - seulement des instructions retirées (INST_SIMD_ALU...) : le roofline CPU sur Mac sera **estimé, pas mesuré**.
- **Bande passante DRAM** : retirée de `powermetrics` (asitop parse un champ mort) - diagnostic mémoire v1 = miss cache + trafic estimé (les événements `LD_SRC_MEMSYS_*` sur M3+ aident).
- **powermetrics** (sudo, `--format plist`) : seule source utilisable sans Xcode - fréquences/résidences par cluster, puissance CPU/GPU/ANE, instructions+cycles par processus.
- **xctrace** : exige Xcode complet, non redistribuable (SLA) mais on peut invoquer la copie de l'utilisateur ; export XML ; attache à un process tiers via l'autorisation "developer tools".
- **GPU Metal** sans modifier l'app : MTLCounterSampleBuffer exclu (in-process) ; voies viables = Metal System Trace via xctrace (150+ compteurs, limiters ALU/bandwidth, occupancy) et MTL_HUD en mode launch.
- **Implication spec** : v1 macOS = mode launch avec sudo, détection de capacités (Xcode ? root ?), métriques étiquetées « mesuré » vs « estimé ».

Détails sourcés : `docs/research/apple-silicon.md` sur la branche `research/apple-silicon` (commit 2106c9d).
