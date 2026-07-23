# Recherche : collecte de métriques sur Apple Silicon (M1-M5)

Type: research
Status: claimed

## Question

Que peut-on réellement collecter sur macOS Apple Silicon pour alimenter un roofline et des diagnostics mémoire, sans instrumentation du code ?

À établir depuis les sources primaires (docs Apple, man pages, projets open source) :
- Compteurs CPU : kperf/kpc (framework privé ?), `xctrace` et ses exports, `powermetrics` - qu'est-ce qui est utilisable par un outil tiers redistribuable, avec quelles permissions (sudo, entitlements) ?
- Compteurs GPU (Metal) : que expose Metal System Trace / MTLCounterSampleBuffer pour un binaire qu'on ne contrôle pas ?
- Quelles métriques roofline (FLOPs, bande passante mémoire) sont atteignables, et lesquelles sont impossibles ?
- Comment des projets existants font (asitop, macpm, Instruments) et ce que ça implique pour notre orchestration.
