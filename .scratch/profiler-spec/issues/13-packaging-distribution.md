# Décision : packaging et distribution

Type: grilling

## Question

Comment la librairie est-elle installée et distribuée pour rester « simple à mettre en place » sur cluster HPC, poste Linux et Mac ?

Le ticket 04 a établi que tous les collecteurs sont orchestrés en sous-processus (aucun linkage) : un paquet Python pur avec assets TS précompilés est donc plausible. Trancher : pip/PyPI seul ou aussi conda-forge et spack ; politique vis-à-vis des collecteurs absents (installation guidée ? bundling interdit pour nsys/ncu - EULA) ; versions Python supportées ; comment la commande `doctor` (ticket 04) s'articule avec l'installation.

Note issue du ticket 12 : Node.js + pi (pi.dev) sont des prérequis REQUIS - le packaging doit couvrir leur détection/installation guidée, y compris sur cluster sans droits admin.

Note issue du ticket 05 : **l'hypothèse « paquet Python pur » tombe**. Le noyau de calibration embarque des kernels en intrinsics par ISA, du PTX (NVIDIA) et des objets code `gfx` (AMD) : il faut des wheels binaires par plateforme (manylinux x86-64/aarch64, macOS arm64) avec dispatch d'ISA à l'exécution, une matrice de build CI correspondante, et un chemin de recompilation locale pour les ISA non couvertes. À trancher ici : quelles cibles `gfx` sont dans la wheel, et comment conda-forge/spack s'articulent avec ces artefacts binaires. Cas particulier : la sonde réseau ne peut pas être précompilée (liaison à la pile MPI du site) et se construit avec le `mpicc` local - le packaging doit donc embarquer ses sources et un chemin de build, et la commande `doctor` doit savoir dire si `mpicc` est utilisable.

Note issue du ticket 07 : la wheel doit **aussi** embarquer un symboliseur permissif (Mach-O et ELF, `.dSYM`, `.gnu_debuglink`, DWARF 4/5, chaînes d'inlining, démanglage C++/Rust/Fortran) et les **briques LLVM** qui servent à la fois la symbolisation et l'analyse statique de boucle (désassembleur, modèles d'ordonnancement par microarchitecture). À trancher ici : LLVM lié en bibliothèque ou binaire `llvm-symbolizer` embarqué, l'impact réel sur la taille de la wheel (l'ordre de grandeur de la dizaine de mégaoctets a été avancé sans être vérifié, et il faut le mesurer avant de s'engager), et l'articulation avec conda-forge et spack qui, eux, préféreront dépendre du LLVM du système. Le repli en sous-processus reste `llvm-symbolizer`/`addr2line` sur Linux et `atos` sur macOS, tous deux exécutables mais **jamais redistribuables** (GPL pour binutils, Xcode pour `atos`) : la politique de bundling doit les traiter comme `nsys`/`ncu`. Le ticket 07 ajoute enfin `profiler compare` à la surface CLI et fait de py-spy une dépendance du chemin Python en dehors de CPython 3.12+ sous Linux.
