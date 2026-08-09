# 11 - Interface en ligne de commande

Référence : [ADR 0007](../adr/0007-surface-cli.md).

## Où vit l'état

**Un Run est un répertoire auto-suffisant.** Ni registre, ni identifiant : le nom du dossier *est* l'identifiant. Un Run naît dans un job, atterrit sur `$SCRATCH`, puis est copié, archivé, joint à un ticket, envoyé à un collègue - un répertoire survit à tout cela, un identifiant dans un magasin local ne survit pas au premier `scp`.

> **Tout ce qui décrit un Run vit dans le Run. Le cache global ne contient que ce qui est recalculable.** Perdre le cache coûte du temps, jamais une information.

**Emplacement** : `.nunatak/PROJET-AAAAMMJJ-HHMMSS/`.

Le nom du projet suit une cascade : celui déclaré dans `nunatak.toml`, sinon le nom du dépôt git, sinon le **nom de base du binaire cible réel**, `--name` l'emportant toujours. Attention au piège : dans `nunatak run -- mpirun -n 256 ./solveur`, le nom attendu est `solveur` et non `mpirun`. La machinerie qui voit à travers le lanceur existe déjà pour `doctor` ; on la réutilise.

- clé `runs_dir` (défaut `.nunatak`) pour déplacer le parent, typiquement vers `$SCRATCH` ;
- `-o` pour désigner exactement le répertoire du Run ;
- `.nunatak/.gitignore` contenant `*` écrit automatiquement, sans toucher au `.gitignore` de l'utilisateur ;
- `run` **affiche le chemin du Run à la fin**, le dossier étant caché ;
- les commandes qui prennent un Run acceptent de ne pas en recevoir et prennent **le plus récent** de `runs_dir`. C'est le confort d'un registre sans en être un : « le plus récent » se lit sur les noms de dossiers, il n'y a aucun index à réparer.

**Cache global** sous `$XDG_CACHE_HOME/nunatak`, **partagé entre nœuds** - un `TMPDIR` local au nœud serait le mauvais endroit, la Calibration devant survivre au job. Il contient les Calibrations par Machine, les sondes réseau construites par pile MPI, et les accords d'envoi de source.

## Les six verbes

| Commande | Rôle |
|---|---|
| `nunatak run -- <commande>` | Mesure, analyse, rapport. Déterministe, sans réseau. |
| `nunatak doctor [-- <commande>]` | Diagnostic. Construit la sonde réseau, recompile localement au besoin. Sans la commande cible, il ne peut pas inspecter le binaire. |
| `nunatak explain [<run>]` | Génère ou régénère les Explications. |
| `nunatak report [<run>]` | Régénère le rapport depuis le pivot. |
| `nunatak compare <runA> <runB>` | Diff entre deux Runs. |
| `nunatak calibrate` | Idempotente, respecte le cache, `--force` pour refaire. |

**`report` n'est pas un doublon** : le Diagnostic n'est jamais persisté mais recalculé, donc régénérer est une opération réelle - après un `explain`, après une montée de version, ou pour produire une variante `--no-source` partageable sans reprofiler.

**`calibrate` reste automatique au premier Run** ; l'exposer permet de la faire dans un petit job dédié plutôt qu'au début d'une grosse allocation.

## Ce que `doctor` vérifie

- l'inventaire des trois catégories d'outils externes (chapitre 12) avec leurs **versions** ;
- les permissions : niveau `paranoid` de perf, `ERR_NVGPUCTRPERM` ;
- le binaire cible : `-g`, frame pointers, `-lineinfo`, présence d'un `.dSYM` ou d'une carte de debug ;
- l'utilisabilité de `mpicc`, et il construit la sonde réseau ;
- la version de LLVM et la couverture `-mcpu` de la microarchitecture détectée.

**Deux règles de méthode**, tirées de faits constatés :

- **ne jamais se fier à `xcrun --find`** : sur une machine où `xcode-select` pointe vers un Xcode désinstallé, il déclare absents `dsymutil`, `nm` et `atos` qui sont pourtant dans `/usr/bin` ;
- **ne jamais se fier au seul `PATH`** : la formule Homebrew `llvm` est `keg_only`, donc jamais liée.

`doctor` **sonde les chemins et invoque les outils**. Constater une présence ne suffit pas.

Un **sous-ensemble bon marché s'exécute automatiquement au début de `run`** - pas de construction, pas de benchmark, quelques dizaines de millisecondes. Il annonce ce qui sera dégradé **puis continue**.

## Drapeaux

| Drapeau | Effet |
|---|---|
| `--strict` | toute dégradation nommée devient une erreur |
| `--no-source` | retire le texte du code du rapport ; les lignes et métriques restent |
| `--source-map A=B` | correspondance de chemins de sources |
| `--call-graph dwarf` | piles par recopie de pile, opt-in, coût annoncé, fréquence abaissée |
| `--no-explain` | n'appelle pas le modèle |
| `--name` | force le nom du projet |
| `-o` | désigne le répertoire du Run |
| `--json` | sortie machine, sur `doctor`, `run` et `compare` |
| `--force` | sur `calibrate` |

Le mode multi-passes et le backend kperf sont exposés comme options expertes, jamais par défaut.

## Codes de sortie

**Le code de sortie de l'application est propagé** : nunatak observe, il ne masque pas. Sans cela, `nunatak run -- mpirun ./solveur && post_traitement` enchaînerait sur des résultats cassés.

| Code | Signification |
|---|---|
| celui de l'application | cas général |
| `127` | commande introuvable |
| `126` | trouvée mais non exécutable |
| `125` | échec de nunatak avant le lancement |
| `121` | violation de `--strict` |

Ambiguïté assumée et documentée : une application sortant elle-même en 125 est indiscernable d'un échec de nunatak. C'est le prix de la transparence, `timeout` le paie aussi, et la sortie JSON tranche quand il faut une certitude.

**Sans `--strict`, une dégradation ne fait jamais sortir en erreur.** Un run réussi avec un roofline estimé renvoie 0.

## Configuration

**Trois couches, par précédence croissante** : site, projet, drapeaux. Format TOML, `nunatak.toml` à la racine du dépôt - **jamais dans `pyproject.toml`**, l'application profilée étant rarement en Python.

Elles servent deux besoins que la ligne de commande ne couvre pas : un **site** qui veut des défauts pour tous ses utilisateurs (provider local, `--no-source` systématique, chemin du `perf` utilisable, `runs_dir` vers `$SCRATCH`), un **projet** qui veut mémoriser sa correspondance de sources.

**Le provider et le modèle n'y figurent jamais** : la configuration de Pi reste la source unique.

**La configuration effective est enregistrée dans la Provenance, seuils de Qualité compris.** On peut régler un seuil, on ne peut pas le régler en douce.

## Sortie terminal

C'est une sortie de première classe : sur un cluster, l'affichage de `run` atterrit dans un **fichier de log de job**, pas dans un terminal.

- **Elle détecte son support.** Sur un terminal : couleur et diffusion au fil de l'eau de la génération du modèle. Hors terminal : ni couleur, ni réécriture de ligne, ni barre de progression, mais des lignes horodatées lisibles dans un `tail -f` comme dans un fichier relu trois semaines plus tard.
- **Trois moments** : le `doctor` léger avant le lancement ; l'avancement aux étapes réelles pendant - Calibration, Passe, rapatriement par rang, analyse - **sans fausse précision sur le temps restant** ; le résumé à la fin, qui reprend le premier niveau du rapport puis les dégradations puis les chemins.
- **Même vocabulaire que le rapport.**
