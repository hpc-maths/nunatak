# Décision : modèle de données unifié (kernels, métriques, traces)

Type: grilling
Blocked by: 03, 04
Status: resolved

## Question

Quel est le modèle de données pivot de la librairie - la représentation unique vers laquelle tous les collecteurs convergent et depuis laquelle analyse, rapport et LLM travaillent ?

À modéliser (session /domain-modeling) : les entités (run, rang MPI, device, kernel/région, échantillon, compteur, métrique dérivée, plafond machine), leurs relations, la granularité temporelle, et le format de persistance (schéma sur disque pour les gros runs - parquet, sqlite, autre). Ce modèle est le cœur de l'architecture : chaque backend de collecte s'y projette.

Note issue des tickets 02 et 03 : chaque métrique doit porter une qualité (« mesuré » vs « estimé » vs « indisponible ») - imposé par macOS (pas de compteur FLOPs) et par les microarchitectures aux compteurs absents ou non fiables (Haswell, Sandy Bridge, E-cores, Zen 2/3).

## Answer

Modèle pivot arrêté en session /domain-modeling (glossaire dans `CONTEXT.md`, décision dans `docs/adr/0001-modele-de-donnees-pivot.md`).

**Entités du pivot mesuré** (seule chose persistée) :
- **Hotspot** : unité atomique unifiée - fonction (CPU/DWARF), kernel groupé par nom (GPU), frame (Python). Le « kernel » du brief.
- **Locus** : point de la topologie d'exécution, en niveaux (nœud > rang MPI > thread ; nœud > device > stream). Axe « où ».
- **Mesure** : valeur attachée à un couple (Hotspot, Locus). Grain élémentaire. Agrégation entre loci (dont déséquilibre de charge) calculée à la demande.
- **Compteur brut** vs **Métrique dérivée** : le premier est ce que le collecteur rapporte, le second est calculé via une Formule et mémorise son Linéage (compteurs sources).
- **Qualité** (« mesuré / estimé / indisponible ») : portée par chaque Mesure, se propage automatiquement le long du Linéage (pire des entrées).
- **Événement** : fait horodaté avec durée (lancement kernel, appel MPI). Flux distinct des Mesures, alimente timeline et analyse réseau.
- **Run** : conteneur d'une session ; **Machine** : entité distincte partagée entre Runs, porteuse des plafonds roofline.

**Séparation des couches** : le pivot mesuré est persisté ; le **Placement roofline** et le **Diagnostic** déterministe sont recalculés à la demande (reproductibles) ; l'**Explication** LLM est persistée séparément et étiquetée « conseil ».

**Persistance** : Parquet colonnaire (Mesures + Événements) + manifeste JSON ; jointures via DuckDB, sans serveur. Alternatives SQLite et Parquet+index SQLite écartées (voir ADR).
