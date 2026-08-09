# Surface CLI : le Run est un répertoire, six verbes, et rien qui masque

## Contexte et décision

Six tickets avaient chargé la CLI de responsabilités sans jamais la dessiner : `doctor` a accumulé l'inventaire des outils, les permissions, l'inspection du binaire cible et la construction de la sonde réseau ; `compare` et `--strict` sont entrés en v1 ; `--no-source`, `--source-map` et le mode multi-passes se sont ajoutés en chemin. Ce ticket assemble.

**Un Run est un répertoire auto-suffisant, pas une entrée dans un magasin.** Il n'y a ni registre ni identifiant : le nom du dossier *est* l'identifiant. La raison est propre au HPC : un Run naît **dans un job**, sur des nœuds de calcul, avec une sortie qui atterrit sur `$SCRATCH` et non dans un `$HOME` au quota serré, puis il est copié, archivé, joint à un ticket, envoyé à un collègue. Un répertoire survit à tout cela ; un identifiant dans un magasin local ne survit pas au premier `scp`. Le ticket 06 allait déjà dans ce sens en faisant du Run le conteneur persisté, et le ticket 07 y a embarqué la Provenance pour qu'il s'explique tout seul.

D'où la règle qui gouverne tout l'état du produit :

> **Tout ce qui décrit un Run vit dans le Run. Le cache global ne contient que ce qui est recalculable.** Perdre le cache coûte du temps, jamais une information.

**L'Explication du LLM est séparée de la mesure par nécessité, pas par confort.** Le ticket 08 avait relevé 24 à 60 secondes par kernel, ce qui plaidait déjà pour ne pas bloquer. Mais le motif décisif est ailleurs : `run` s'exécute dans un job, sur des nœuds de calcul qui n'ont **généralement aucune sortie réseau**. Mesure et explication ne diffèrent pas seulement par leur durée, elles s'exécutent **à des endroits différents**.

**nunatak observe, il ne masque pas.** Le code de sortie de l'application profilée est propagé tel quel, comme le font `time`, `strace`, `env` et `timeout`.

## Options considérées

- **Un dépôt local géré** (`~/.nunatak`) avec des Runs désignés par identifiant et une commande `list` : écarté, l'identifiant ne survit pas à la copie et `$HOME` est le mauvais système de fichiers sur un cluster.
- **Écrire les Runs à plat dans le répertoire courant** : écarté au profit d'un `.nunatak/` caché, qui garde le répertoire de travail net après vingt runs sans réintroduire de registre.
- **L'Explication comme étape obligatoire de `run`** : écartée, elle rendrait `run` inutilisable dans un job sans sortie réseau.
- **L'Explication comme commande entièrement manuelle** : écartée aussi, elle dégraderait l'expérience sur portable où tout fonctionne du premier coup. `run` tente et dégrade.
- **Renvoyer le statut de nunatak plutôt que celui de l'application** : écarté, `nunatak run -- mpirun ./solveur && post_traitement` enchaînerait alors sur des résultats cassés.
- **Faire sortir en erreur toute dégradation** : écarté, cela casserait tous les `set -e` des scripts de job pour un run parfaitement exploitable. C'est précisément le rôle de `--strict`, et de lui seul.
- **Une section `[tool.nunatak]` dans `pyproject.toml`** : écartée, l'application profilée est le plus souvent en C++ ou en Fortran et n'a aucune raison d'avoir un fichier Python.
- **Dupliquer le provider et le modèle LLM dans notre configuration** : écarté, le ticket 12 a fait de la config de Pi la source unique.
- **Une interface texte animée pendant le run** : écartée, l'affichage atterrit dans un fichier de log de job et non dans un terminal.

## Conséquences

### Où vit l'état

- Les Runs atterrissent dans **`.nunatak/PROJET-AAAAMMJJ-HHMMSS/`**. Le nom du projet suit une cascade : celui déclaré dans `nunatak.toml`, sinon le nom du dépôt git, sinon le **nom de base du binaire cible réel**, `--name` l'emportant toujours.
- Ce dernier point a un piège : dans `nunatak run -- mpirun -n 256 ./solveur`, le nom attendu est `solveur` et non `mpirun`. nunatak sait déjà voir à travers le lanceur puisque `doctor` doit trouver le binaire cible pour l'inspecter ; on réutilise cette machinerie plutôt que d'en écrire une seconde.
- La clé de configuration **`runs_dir`** (défaut `.nunatak`) déplace le parent, typiquement vers `$SCRATCH` sur un site qui le souhaite ; **`-o`** désigne exactement le répertoire du Run quand on veut sortir du schéma.
- Le dossier étant caché, **`run` affiche le chemin du Run à la fin**, et les commandes qui prennent un Run acceptent de ne pas en recevoir : elles prennent alors **le plus récent** de `runs_dir`. C'est le confort d'un registre sans en être un, puisque « le plus récent » se lit sur les noms de dossiers et qu'il n'y a aucun index à tenir à jour ni à réparer.
- nunatak écrit un **`.nunatak/.gitignore` contenant `*`**, ce qui évite de polluer le `git status` de l'utilisateur sans toucher à son propre `.gitignore`.
- **Quel que soit le nombre de rangs, un Run est un seul répertoire.** Les données par rang y sont rapatriées, y compris les `/tmp/perf-<pid>.map` du ticket 07 qu'il faut récupérer avant que l'épilogue du job ne nettoie les nœuds. L'utilisateur n'a jamais 256 dossiers à recoller.
- Le **cache global** vit sous `$XDG_CACHE_HOME/nunatak` et ne contient que du recalculable : Calibrations par Machine (ticket 05), sondes réseau construites par pile MPI (ticket 13), accords d'envoi de source à un provider distant (ticket 07). Il doit être **partagé entre nœuds** : un `TMPDIR` local au nœud de calcul serait le mauvais endroit, la Calibration devant survivre au job. Sa taille est négligeable.

### Les six verbes

| Commande | Rôle |
|---|---|
| `nunatak run -- <commande>` | Mesure, analyse, rapport. Entièrement déterministe, sans réseau. |
| `nunatak doctor [-- <commande>]` | Diagnostic. Construit la sonde réseau, recompile localement un noyau de calibration pour une ISA non couverte. Sans la commande cible, il ne peut pas inspecter le binaire. |
| `nunatak explain <run>` | Génère ou régénère les Explications d'un Run existant. |
| `nunatak report <run>` | Régénère le rapport HTML depuis le pivot. |
| `nunatak compare <runA> <runB>` | Le diff du ticket 07. |
| `nunatak calibrate` | Idempotente, respecte le cache, `--force` pour refaire. |

- **`report` n'est pas un doublon** : le Diagnostic n'est jamais persisté mais recalculé (ticket 06), donc régénérer est une opération réelle - après un `explain`, après une montée de version de nunatak, ou pour produire une variante `--no-source` partageable sans reprofiler.
- **`calibrate` reste automatique au premier Run** comme le ticket 05 l'a décidé ; l'exposer permet de la faire dans un petit job dédié plutôt qu'au début d'une grosse allocation, ce que voudra tout utilisateur averti.
- **`run` tente l'Explication et n'en dépend jamais.** À défaut, il dégrade de façon nommée avec la commande exacte à rejouer : « Explication non générée : aucune route vers le provider depuis ce nœud. Relance `nunatak explain .nunatak/solveur-20260809-1422` depuis un nœud de connexion. » `--no-explain` pour s'en passer délibérément.

### Codes de sortie

- **Le code de l'application est propagé** dans le cas général.
- Plage réservée, à la manière de `timeout` et `env` : **127** commande introuvable, **126** trouvée mais non exécutable, **125** échec de nunatak avant le lancement, **121** violation de `--strict`.
- L'ambiguïté résiduelle est assumée et documentée : une application qui sort elle-même en 125 est indiscernable d'un échec de nunatak. C'est le prix de la transparence, `timeout` le paie aussi, et la sortie JSON tranche quand on a besoin de certitude.
- **Sans `--strict`, une dégradation ne fait jamais sortir en erreur.** Un run qui a réussi avec un roofline estimé renvoie 0.
- **JSON** sur `doctor`, `run` (résumé du Run : totaux, Hotspots au-dessus du plancher, Qualité, dégradations rencontrées) et surtout `compare`, qui est ce qu'une CI de performance consomme réellement, avec l'incertitude statistique portée dans l'écart comme le ticket 07 l'exige. `explain` et `report` n'en ont pas besoin.

### Configuration

- **Trois couches par précédence croissante** : configuration de site, configuration de projet, drapeaux. Format TOML, `nunatak.toml` à la racine du dépôt.
- Elles servent deux besoins que la ligne de commande ne couvre pas : un **site** qui veut des défauts pour tous ses utilisateurs (provider local, `--no-source` systématique, chemin du `perf` utilisable), un **projet** qui veut mémoriser sa correspondance de sources.
- **Le provider et le modèle LLM n'y figurent jamais** : la config de Pi reste la source unique (ticket 12), nunatak ne la duplique ni ne la surcharge.
- **La configuration effective est enregistrée dans la Provenance**, seuils de Qualité compris - seuil de couverture du multiplexage, plancher statistique. Sans cela, un défaut de site changerait silencieusement les résultats, ce qui est exactement la variation invisible que le projet combat depuis le ticket 07. **On peut régler un seuil ; on ne peut pas le régler en douce.**

### Sortie terminal

C'est une sortie de première classe : sur un cluster, l'affichage de `run` atterrit dans un **fichier de log de job**, pas dans un terminal.

- **Elle s'adapte au support et le détecte.** Sur un terminal : couleur, et diffusion au fil de l'eau de la génération du LLM comme le ticket 08 l'avait retenu. Hors terminal : ni couleur, ni réécriture de ligne, ni barre de progression, mais des lignes horodatées qui s'accumulent et restent lisibles dans un `tail -f` comme dans un fichier relu trois semaines plus tard.
- **Trois moments, trois contenus** : avant le lancement, le sous-ensemble léger de `doctor` annonce ce qui sera dégradé et la marche à suivre ; pendant, l'avancement aux étapes réelles - Calibration, Passe, rapatriement par rang, analyse - sans fausse précision sur le temps restant ; à la fin, un résumé qui reprend le **premier niveau du rapport** du ticket 14, soit les constats avec leur part du temps et leur chiffre-clé, puis les dégradations, puis les chemins du Run et du rapport.
- **Le vocabulaire du terminal est celui du rapport.** Qualité et Niveau de résolution s'y écrivent avec les mêmes mots, et une valeur rétrogradée y affiche sa raison. Qui ne lit que le log apprend moins de détails, jamais moins sur la solidité de ses chiffres.
