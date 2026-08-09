# Modèle de données pivot : Parquet colonnaire, pivot mesuré séparé de l'analyse

## Contexte et décision

Tous les collecteurs hétérogènes (perf, nsys/ncu, rocprofv3, mpiP, perf-trampoline) convergent vers un pivot unique. Ce pivot ne contient que des **données mesurées** : des Hotspots (unité atomique : fonction CPU / kernel GPU / frame Python), observés à des Loci (nœud > rang MPI > thread, ou nœud > device > stream), portant des Mesures agrégées et un flux d'Événements horodatés, plus une référence à la Machine (porteuse des plafonds roofline). Le Placement roofline et le Diagnostic déterministe sont **recalculés à la demande** depuis ce pivot ; l'Explication du LLM est persistée **à part** et étiquetée « conseil ». Le pivot est persisté en **Parquet** (Mesures et Événements colonnaires) + un **manifeste JSON** décrivant le Run et embarquant un instantané complet de la Machine ; les jointures se font à la volée via DuckDB, sans serveur.

> Amendement (ticket 05, ADR 0002) : le manifeste *pointait* initialement la Machine. Comme le Placement roofline est recalculé à la demande, un Run privé de ses Plafonds cesse d'être analysable ; le manifeste embarque donc l'instantané complet du profil Machine, et le cache de calibration n'est plus qu'une optimisation.

## Options considérées

- **SQLite** : jointures relationnelles naturelles et fichier unique portable, mais moins performant sur les gros volumes d'Événements et la lecture colonnaire massive des runs distribués.
- **Parquet + index SQLite** : le plus performant à grande échelle, écarté pour la v1 car deux formats à garder cohérents.

## Conséquences

- Chaque Mesure porte une Qualité (« mesuré / estimé / indisponible ») qui se propage automatiquement le long du Linéage des Métriques dérivées - contrainte imposée par macOS (pas de compteur FLOPs) et les microarchitectures aux compteurs non fiables (Haswell, Sandy Bridge, E-cores, Zen 2/3).
- Le moteur d'analyse peut être amélioré et ré-appliqué à un Run existant sans reprofiler.
- La frontière faits déterministes / conseils LLM est matérialisée jusque sur le disque.
- L'agrégation entre Loci (somme, moyenne, déséquilibre de charge) est toujours calculée à la demande, jamais stockée.
