# Recherche : inventaire des collecteurs à orchestrer

Type: research
Status: claimed

## Question

Quel collecteur précis orchestrer pour chaque plateforme/métrique de la v1, et sous quelles contraintes (interface, format de sortie, licence, droits) ?

À établir depuis les sources primaires (docs, dépôts, licences) :
- CPU Linux : LIKWID (CLI vs pylikwid, GPL - implications quand on l'exécute vs qu'on le linke) vs perf_events direct (perf CLI, perf.data, paranoid levels) - lequel comme backend principal, lequel en secours ?
- GPU NVIDIA : CUPTI direct vs `ncu`/`nsys` CLI et leurs formats de sortie (sqlite, csv) ; permissions requises (ERR_NVGPUCTRPERM).
- GPU AMD : rocprofiler v1/v2/v3 (l'API a beaucoup bougé) - laquelle est stable, quels formats.
- MPI : interception PMPI maison vs Score-P/OTF2 vs mpiP - lequel donne les latences réseau par rang avec le moins de friction d'installation.
- Python : py-spy, perf avec perf-trampoline (CPython 3.12+), viztracer - quel chemin pour attribuer les échantillons au code Python.
- Pour chaque choix : format de sortie parsable, stabilité de l'interface, licence compatible BSD-3/MIT, besoin de droits root/capabilities.
