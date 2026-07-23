# Décision : modèle de données unifié (kernels, métriques, traces)

Type: grilling
Blocked by: 03, 04

## Question

Quel est le modèle de données pivot de la librairie - la représentation unique vers laquelle tous les collecteurs convergent et depuis laquelle analyse, rapport et LLM travaillent ?

À modéliser (session /domain-modeling) : les entités (run, rang MPI, device, kernel/région, échantillon, compteur, métrique dérivée, plafond machine), leurs relations, la granularité temporelle, et le format de persistance (schéma sur disque pour les gros runs - parquet, sqlite, autre). Ce modèle est le cœur de l'architecture : chaque backend de collecte s'y projette.
