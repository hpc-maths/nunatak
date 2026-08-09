# 04 - Architecture

Aucun ticket de conception n'a couvert ce chapitre : il assemble les contraintes posées ailleurs et en tire une découpe. Les frontières décrites ici sont **prescriptives** ; les choix de bibliothèques à l'intérieur d'un composant ne le sont pas.

## Vue d'ensemble

```
                    ┌──────────────────────────────────────┐
                    │  CLI  (run, doctor, explain, report, │
                    │        compare, calibrate)           │
                    └───────────────┬──────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐        ┌─────────▼─────────┐       ┌─────────▼────────┐
│  Diagnostic    │        │  Orchestration    │       │   Inspection     │
│  d'environnement│       │  de la collecte   │       │   (doctor)       │
└────────────────┘        └─────────┬─────────┘       └──────────────────┘
                                    │  sous-processus
                    ┌───────────────┴───────────────┐
                    │        Adaptateurs            │
                    │  perf · nsys/ncu · rocprofv3  │
                    │  mpiP · py-spy · xctrace      │
                    │  sonde réseau · noyau de      │
                    │  calibration                  │
                    └───────────────┬───────────────┘
                                    │  sorties brutes
                    ┌───────────────▼───────────────┐
                    │          Ingestion            │
                    │  parseurs versionnés          │
                    │  normalisation en offsets     │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │         Attribution           │
                    │  symbolisation · inlining     │
                    │  résolution du source         │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │      PIVOT MESURÉ (Run)       │
                    │  Parquet + manifeste JSON     │
                    └───────────────┬───────────────┘
                                    │  lecture seule
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐        ┌─────────▼─────────┐       ┌─────────▼────────┐
│ Analyse        │        │  Explication      │       │  Rendu           │
│ déterministe   │───────▶│  (subprocess pi)  │──────▶│  terminal · HTML │
└────────────────┘        └───────────────────┘       └──────────────────┘
```

## La règle de découpe

**Le pivot mesuré est la seule frontière qui compte.** Tout ce qui est en amont écrit dans le pivot et n'en lit jamais le résultat d'analyse ; tout ce qui est en aval lit le pivot et **ne le modifie jamais**.

Cette frontière n'est pas décorative. Elle est ce qui permet de rejouer une analyse sur un Run de six mois, de régénérer un rapport après une montée de version, de régénérer une Explication sans reprofiler, et de tester tout l'aval sans matériel (chapitre 13).

## Les composants

### Amont du pivot

**Orchestration de la collecte.** Décide quels collecteurs lancer, avec quels paramètres, sur quels rangs, en combien de Passes. Compose l'environnement du lancement (`PYTHONPERFSUPPORT`, `LD_PRELOAD` pour mpiP), lance l'application, rapatrie les artefacts depuis tous les nœuds. C'est le seul composant qui connaît le lanceur MPI.

**Adaptateurs.** Un par outil externe. Un adaptateur sait : détecter la présence et la **version** de son outil, construire sa ligne de commande, l'exécuter, et déclarer ce qu'il produit (Mesures, Événements, ou les deux). Il ne sait rien du pivot.

**Ingestion.** Un parseur par couple (outil, version détectée). C'est ici que se fait la **normalisation en offsets de module** (invariant I3) : aucune adresse absolue ne franchit cette frontière.

**Attribution.** Symbolisation, chaînes d'inlining, règle d'étendue, résolution et vérification du source. Consomme des `(module, offset)` et produit des Hotspots identifiés avec leur Niveau de résolution. C'est le composant le plus dense de la spec et il a son chapitre (06).

### Le pivot

**Run.** Un répertoire. Parquet pour les Mesures et les Événements, JSON pour le manifeste. Aucune sortie d'analyse.

### Aval du pivot

**Analyse déterministe.** Placement roofline, classification, propagation de la Qualité, plancher statistique, déséquilibre entre Loci, analyse statique de boucle. Fonction pure du couple (pivot, Machine). Ne persiste rien.

**Explication.** Assemble un prompt à partir du Diagnostic et du source, pilote `pi` en sous-processus, reçoit les conseils. Le prompt est une **fonction pure du pivot**, ce qui le rend testable par instantané (chapitre 13).

**Rendu.** Deux sorties d'une même synthèse : le résumé terminal et le rapport HTML. Elles partagent le vocabulaire et le premier niveau de contenu.

## Les frontières de processus

Le produit est un **orchestrateur de processus**, pas une bibliothèque monolithique. Quatre types de frontières, toutes franchies en sous-processus :

| Franchissement | Raison |
|---|---|
| Collecteurs tiers (perf, nsys, rocprofv3, mpiP, py-spy, xctrace) | licence (GPL) et découplage d'ABI |
| Outillage LLVM (`llvm-symbolizer`, désassembleur) | dépendance externe versionnée, non embarquée |
| Nos propres binaires (noyau de calibration, sonde réseau) | cohérence du principe, et **justesse de mesure** : calibrer depuis un processus Python résident polluerait la borne recherchée |
| Modèle de langage (`pi` via Node.js) | isolation d'un écosystème entier |

**Conséquence à assumer** : le produit ne fonctionne pas sans savoir lancer des processus et lire leurs sorties. C'est un choix, pas un accident.

## Stack

- **Cœur** : Python. Versions supportées : celles que CPython supporte encore en amont.
- **Rapport** : mini-app TypeScript compilée, embarquée comme asset statique. Aucune requête externe à l'exécution.
- **Binaires propres** : noyau de calibration (intrinsics par ISA, PTX, objets `gfx`) et sonde réseau (liée à la pile MPI du site, donc construite localement).
- **Outillage externe requis** : LLVM 19 ou plus récent, en dépendance déclarée.

Le cœur en Python est possible **parce que** rien n'y est en chemin critique : Python orchestre, parse et analyse des agrégats, il ne compte pas d'événements dans une boucle chaude.

## Ce que l'architecture doit rendre possible

Contraintes de conception qui découlent des autres chapitres, et par lesquelles toute proposition de découpe doit être jugée :

1. **Ajouter un collecteur** ne doit toucher qu'un adaptateur et un parseur.
2. **Une nouvelle version d'un outil** ne doit ajouter qu'un parseur, sans modifier les anciens.
3. **Rejouer l'aval sur des sorties enregistrées** doit être possible sans matériel ni collecteur installé. C'est ce qui rend la stratégie de test du chapitre 13 tenable, et cela impose que les adaptateurs soient **substituables par une source d'enregistrements**.
4. **Régénérer rapport et Explication** depuis un Run seul, sans l'application ni la machine d'origine.
5. **Dégrader par composant** : l'absence d'un collecteur retire des Mesures, elle n'empêche jamais le Run.

## Choix laissés à l'implémentation

Signalés comme tels, ils ne sont pas des décisions ouvertes de conception :

- la bibliothèque d'accès à Parquet ;
- la forme exacte du protocole RPC avec `pi` ;
- le découpage interne en modules Python et le framework CLI ;
- le mécanisme de rapatriement des artefacts multi-nœuds, tant qu'il produit un répertoire unique et récupère les cartes de trampolines Python avant l'épilogue du job.
