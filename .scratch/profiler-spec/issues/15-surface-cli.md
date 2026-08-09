# Décision : surface CLI

Type: grilling
Blocked by: 04, 05, 06, 07, 10, 13
Status: resolved

## Question

Quelles commandes, quels drapeaux, quels codes de sortie, et où vivent les Runs ?

Aucun ticket n'a spécifié la CLI, alors que six d'entre eux lui ont ajouté des responsabilités sans jamais la dessiner. Ce qui s'est accumulé :

- **`run`** : `nunatak run -- mpirun ./app` (cadrage de la carte). Exécute un sous-ensemble léger de `doctor` avant de démarrer (ticket 13), déclenche la Calibration au premier Run sur une Machine (ticket 05), et peut enchaîner plusieurs Passes en mode multi-passes explicite (ticket 10).
- **`doctor`** : inventaire des trois catégories d'outils externes, permissions (`paranoid` de perf, `ERR_NVGPUCTRPERM`), inspection du binaire cible (`-g`, frame pointers, `-lineinfo`, `.dSYM`), utilisabilité de `mpicc`, version de LLVM et couverture `-mcpu`, construction de la sonde réseau, sortie JSON (tickets 04, 05, 07, 13). Il ne doit jamais se fier à `xcrun --find` ni au seul `PATH`.
- **`compare runA runB`** : diff minimal en v1, terminal plus rapport HTML, sans historique (ticket 07).
- **Drapeaux déjà décidés ailleurs** : `--strict`, `--no-source`, `--source-map`, `--call-graph dwarf` en opt-in, backend kperf expert.

À trancher : le jeu de verbes et leurs noms ; **où vivent les Runs et comment on les désigne** (chemin, identifiant, dépôt local ?) ; ce que `run` fait par défaut de bout en bout (mesure, analyse, rapport, Explication ?) ; si l'appel au LLM est une étape de `run` ou une commande séparée, sachant que l'Explication est régénérable sans reprofiler (ticket 06) ; s'il existe une commande de Calibration explicite et une de recompilation locale (tickets 05, 13) ; fichier de configuration ou drapeaux seuls ; et les **codes de sortie**, qui comptent dès lors que `--strict` existe pour les usages scriptés.

## Answer

Décision prise en session /grilling ; arbitrage complet dans `docs/adr/0007-surface-cli.md`.

**Un Run est un répertoire auto-suffisant**, sans registre ni identifiant : le nom du dossier *est* l'identifiant. Motif propre au HPC : un Run naît dans un job, atterrit sur `$SCRATCH`, puis est copié, archivé et envoyé à un collègue. Un identifiant dans un magasin local ne survit pas au premier `scp`. Règle générale : **tout ce qui décrit un Run vit dans le Run ; le cache global ne contient que ce qui est recalculable** (Calibrations, sondes réseau construites, accords d'envoi de source), sous `$XDG_CACHE_HOME/nunatak` et partagé entre nœuds.

**Emplacement** : `.nunatak/PROJET-AAAAMMJJ-HHMMSS/`. Le nom du projet suit une cascade (`nunatak.toml`, dépôt git, nom de base du **binaire cible réel vu à travers le lanceur**, `--name` prioritaire). Clé `runs_dir` pour déplacer le parent vers `$SCRATCH`, `-o` pour désigner exactement le répertoire, `.gitignore` auto contenant `*`, chemin affiché en fin de run, et repli sur le Run le plus récent quand aucun n'est donné. **Un Run est un seul répertoire quel que soit le nombre de rangs.**

**Six verbes** : `run` (mesure, analyse, rapport, sans réseau), `doctor` (diagnostic, construit la sonde réseau, recompile localement au besoin), `explain`, `report` (le Diagnostic n'étant jamais persisté, régénérer est une opération réelle), `compare`, `calibrate`.

**L'Explication est séparée par nécessité, pas par confort** : `run` s'exécute sur des nœuds de calcul qui n'ont généralement aucune sortie réseau. Mesure et explication s'exécutent à des endroits différents. `run` tente et dégrade de façon nommée avec la commande exacte à rejouer.

**Codes de sortie** : celui de l'application est **propagé** - nunatak observe, il ne masque pas, sans quoi un `run -- mpirun ./solveur && post_traitement` enchaînerait sur des résultats cassés. Plage réservée à la manière de `timeout` : 127 introuvable, 126 non exécutable, 125 échec avant lancement, **121 violation de `--strict`**. Sans `--strict`, une dégradation ne fait jamais sortir en erreur. **JSON** sur `doctor`, `run` et `compare`.

**Configuration en trois couches** (site, projet, drapeaux), TOML, `nunatak.toml` à la racine et jamais dans `pyproject.toml`. Le provider et le modèle n'y figurent jamais (config de Pi, ticket 12). **La configuration effective est enregistrée dans la Provenance, seuils de Qualité compris** : on peut régler un seuil, on ne peut pas le régler en douce.

**Sortie terminal** de première classe, puisqu'elle atterrit dans un fichier de log de job : elle **détecte le support** (couleur et streaming sur un terminal, lignes horodatées sans réécriture ailleurs), s'organise en trois moments (`doctor` léger, avancement aux étapes réelles, résumé reprenant le premier niveau du rapport du ticket 14), et emploie **le vocabulaire du rapport** - qui ne lit que le log apprend moins de détails, jamais moins sur la solidité de ses chiffres.
