# Décision : packaging et distribution

Type: grilling
Status: resolved

## Question

Comment la librairie est-elle installée et distribuée pour rester « simple à mettre en place » sur cluster HPC, poste Linux et Mac ?

Le ticket 04 a établi que tous les collecteurs sont orchestrés en sous-processus (aucun linkage) : un paquet Python pur avec assets TS précompilés est donc plausible. Trancher : pip/PyPI seul ou aussi conda-forge et spack ; politique vis-à-vis des collecteurs absents (installation guidée ? bundling interdit pour nsys/ncu - EULA) ; versions Python supportées ; comment la commande `doctor` (ticket 04) s'articule avec l'installation.

Note issue du ticket 12 : Node.js + pi (pi.dev) sont des prérequis REQUIS - le packaging doit couvrir leur détection/installation guidée, y compris sur cluster sans droits admin.

Note issue du ticket 05 : **l'hypothèse « paquet Python pur » tombe**. Le noyau de calibration embarque des kernels en intrinsics par ISA, du PTX (NVIDIA) et des objets code `gfx` (AMD) : il faut des wheels binaires par plateforme (manylinux x86-64/aarch64, macOS arm64) avec dispatch d'ISA à l'exécution, une matrice de build CI correspondante, et un chemin de recompilation locale pour les ISA non couvertes. À trancher ici : quelles cibles `gfx` sont dans la wheel, et comment conda-forge/spack s'articulent avec ces artefacts binaires. Cas particulier : la sonde réseau ne peut pas être précompilée (liaison à la pile MPI du site) et se construit avec le `mpicc` local - le packaging doit donc embarquer ses sources et un chemin de build, et la commande `doctor` doit savoir dire si `mpicc` est utilisable.

Note issue du ticket 07 : la wheel doit **aussi** embarquer un symboliseur permissif (Mach-O et ELF, `.dSYM`, `.gnu_debuglink`, DWARF 4/5, chaînes d'inlining, démanglage C++/Rust/Fortran) et les **briques LLVM** qui servent à la fois la symbolisation et l'analyse statique de boucle (désassembleur, modèles d'ordonnancement par microarchitecture). À trancher ici : LLVM lié en bibliothèque ou binaire `llvm-symbolizer` embarqué, l'impact réel sur la taille de la wheel (l'ordre de grandeur de la dizaine de mégaoctets a été avancé sans être vérifié, et il faut le mesurer avant de s'engager), et l'articulation avec conda-forge et spack qui, eux, préféreront dépendre du LLVM du système. Le repli en sous-processus reste `llvm-symbolizer`/`addr2line` sur Linux et `atos` sur macOS, tous deux exécutables mais **jamais redistribuables** (GPL pour binutils, Xcode pour `atos`) : la politique de bundling doit les traiter comme `nsys`/`ncu`. Le ticket 07 ajoute enfin `nunatak compare` à la surface CLI et fait de py-spy une dépendance du chemin Python en dehors de CPython 3.12+ sous Linux.

## Answer

Décision prise en session /grilling ; arbitrage complet dans `docs/adr/0005-packaging-distribution.md`.

**Principe organisateur** : conda-forge et spack livrent un **produit complet** (LLVM, Node, pi, py-spy en dépendances déclarées) ; PyPI livre le **cœur** et déclare ce qui manque, `doctor` donnant la commande exacte pour compléter. Un seul comportement, deux niveaux de complétude.

**LLVM en dépendance externe, jamais vendorisé** - revirement par rapport au ticket 07, fondé sur deux faits : une wheel embarquant LLVM pèse **40 à 60 Mo** (mesuré sur `llvmlite`), pas « une dizaine de mégaoctets » ; et spack comme conda-forge, qui portent réellement la distribution, refusent le vendoring. L'exigence du ticket 07 est redirigée : la variation entre sites est acceptée parce que la **Provenance enregistre la version de LLVM et le `-mcpu` retenu**.

**`llvm@19:`** en dépendance déclarée. Mesuré sur les tables de microarchitectures : 17 apporte znver4/sapphirerapids/graniterapids/apple-m1-m2/neoverse-v2, 18 ajoute apple-m3, **19 ajoute znver5, apple-m4, neoverse-v3 et n3**, 20 ajoute diamondrapids. Un plancher plus bas dégraderait l'outil sur le matériel neuf. **17 et 18 tolérés** en couverture réduite ; en dessous, repli sous-processus du ticket 07. La sûreté est mécanique : microarchitecture absente de la liste `-mcpu` de la version installée → bornes de cycles « indisponible », jamais de résultat faux.

**Deux familles dans l'analyse statique** : les comptages (vectorisation, motif d'accès, **intensité L1**) ne dépendent que du désassembleur, les bornes de cycles du modèle d'ordonnancement. Corrige l'ADR 0004 : le roofline estimé de macOS ne dépend pas de la finesse du modèle Apple. L'analyse statique ne produit **jamais** de « mesuré ».

**Veille outillée** : LLVM sort une majeure tous les six mois à date prévisible. CI sur chaque rc, **diff automatique des `-mcpu`** ouvrant un ticket, **corpus de binaires figés** en non-régression, borne haute ouverte avec avertissement sans refus au-delà de la fenêtre testée, veille étendue à tous les outils orchestrés, cadence de release propre.

**Node et pi alignés sur le motif commun** de dégradation nommée (assouplit le ticket 12) : déclarés sur conda et spack, absents ailleurs ils donnent « Explication indisponible », et le run se déroule.

**Binaires autonomes plutôt que modules d'extension** : le noyau de calibration et la sonde réseau sont des exécutables invoqués en sous-processus. Cohérent avec « exec + parse » du ticket 04 ; wheel `py3-none-<plateforme>`, donc **un artefact par plateforme et non par version de Python** ; et Calibration mesurée dans un processus propre, donc borne plus juste. **Python : support amont CPython** (3.11 à 3.14 aujourd'hui), sans politique maison.

**GPU** : PTX seul côté NVIDIA, le pilote assurant la compatibilité ascendante. Côté AMD, **`gfx90a`, `gfx942`, `gfx908`**, le reste en recompilation locale, asymétrie documentée comme un choix (cibles génériques ROCm à évaluer). **CPU** : dispatch d'ISA à l'exécution, nécessaire pour ne pas produire un plafond faux étiqueté « mesuré ».

**Sonde réseau construite au premier usage**, jamais à l'installation : sur un cluster à modules, le MPI de l'installation n'est presque jamais celui du job. Cache par `(implémentation, version, mpicc)`, construction de préférence pendant `doctor`, pile MPI enregistrée dans la Provenance, absence de `mpicc` → analyse MPI indisponible. **Le mécanisme couvre aussi mpiP**, qui se lie lui aussi à la pile du site. MPI 5.0 (approuvé le 5 juin 2025) normalise un ABI : à surveiller, pas à parier dessus.

**Trois catégories d'outils externes** : livrés par nos canaux / construits localement / fournis par le site et jamais redistribuables (`nsys`, `ncu`, `perf`, rocprofv3, LIKWID). Pour la troisième, on détecte, on nomme la capacité perdue, on indique comment le site la fournit - aucune installation guidée qui téléchargerait quoi que ce soit.

**`doctor`** : un sous-ensemble bon marché s'exécute automatiquement au début de `run`, annonce les dégradations et continue ; **`--strict`** les transforme en erreurs ; sortie **JSON** pour la CI. Ne se fie jamais à `xcrun --find` (qui ment quand `xcode-select` pointe vers un Xcode désinstallé) ni au seul `PATH` (la formule Homebrew `llvm` est `keg_only`) : il sonde les chemins et invoque les outils.
