# Packaging : conda-forge et spack livrent un produit complet, PyPI livre le cœur

## Contexte et décision

Trois tickets avaient chargé ce sujet sans le trancher. Le ticket 05 a fait tomber l'hypothèse du paquet Python pur en imposant un noyau de calibration binaire par ISA. Le ticket 12 a fait de Node.js et de pi des prérequis. Le ticket 07 y a ajouté un symboliseur et les briques LLVM de l'analyse statique de boucle. La question n'était donc plus « comment publier un paquet » mais « que contient l'artefact, et qui fournit le reste ».

**Le principe qui organise tout le reste** : les canaux **conda-forge et spack livrent un produit complet**, en tirant LLVM, Node, pi et py-spy comme dépendances déclarées ; le canal **PyPI livre le cœur** et déclare ce qui manque, `doctor` donnant la commande exacte pour compléter. Un seul comportement, deux niveaux de complétude, aucune divergence de code entre canaux.

**LLVM est une dépendance externe, jamais vendorisée.** C'est un revirement par rapport au ticket 07, qui avait choisi d'embarquer le symboliseur pour que le comportement ne varie pas d'un site à l'autre. Deux faits ont renversé l'arbitrage. D'abord la mesure : `llvmlite`, le précédent le plus proche d'une wheel Python embarquant LLVM, pèse **40 Mo sur macOS arm64 et 58 à 60 Mo en manylinux**, contre l'ordre de grandeur d'une dizaine de mégaoctets avancé sans vérification au ticket 07. Ensuite la réalité du terrain : spack est présent sur la quasi-totalité des machines HPC et conda-forge sur la plupart des postes de développement, or **ces deux canaux refusent le vendoring par culture** et livrent aujourd'hui LLVM 22.

L'argument du ticket 07 n'est pas abandonné, il est **redirigé** : ce qui comptait était que l'identité d'un Hotspot ne varie pas en silence. La variation est désormais acceptée parce qu'elle est **enregistrée dans la Provenance** - version exacte de LLVM et `-mcpu` réellement retenu. Une variation inscrite dans le Run n'est plus une variation cachée.

## Options considérées

- **Vendoriser LLVM partout, y compris dans conda-forge et spack** : cohérent avec le ticket 07, écarté parce qu'un paquet qui embarque son propre LLVM se fait recaler en revue conda-forge, et parce que 50 Mo par plateforme pour une fonctionnalité que la moitié des utilisateurs ne regardera pas est un mauvais échange.
- **Vendoriser uniquement dans la wheel PyPI**, conda et spack se liant au système : écarté, c'est le pire des deux mondes, deux comportements pour un même produit selon le canal d'installation.
- **Abandonner PyPI** puisque spack et conda-forge portent la distribution : écarté, `pip install` dans un venv reste le premier réflexe de tout le monde et souvent la seule chose faisable sans droits admin.
- **Plancher LLVM à 17**, la version de RHEL 8 : écarté après mesure. Zen 5, Apple M4 et Neoverse V3 n'arrivent qu'en **LLVM 19**, et Diamond Rapids en 20 : un plancher bas dégrade l'outil précisément sur le matériel neuf, celui dont personne n'a l'habitude et dont on ne connaît pas les pièges.
- **Refuser une version de LLVM hors de la fenêtre testée** : écarté, cela condamnerait l'utilisateur d'un conda-forge à jour à attendre notre release pour un risque le plus souvent inexistant.
- **Lier la cadence de release de nunatak à celle de LLVM** : écarté, cadence propre, LLVM restant une dépendance comme une autre.
- **Prérequis dur pour Node et pi** (décision du ticket 12) : assoupli, voir plus bas.
- **Noyau de calibration en module d'extension Python** : écarté au profit d'exécutables autonomes, voir plus bas.
- **Construire la sonde réseau à l'installation** : écarté, sur un cluster à modules le MPI de l'installation n'est presque jamais celui du job.
- **Installation guidée téléchargeant les collecteurs propriétaires** : écarté, l'EULA NVIDIA l'interdit pour `nsys` et `ncu`, et télécharger des outils sur une machine partagée n'est de toute façon pas notre rôle.

## Conséquences

### Canaux et dépendances

- **conda-forge et spack** sont les canaux de référence. Ils déclarent LLVM, Node.js, pi et py-spy en dépendances, donc l'utilisateur obtient un produit complet sans démarche supplémentaire. `conda-forge` couvre `linux-64`, `linux-aarch64`, `linux-ppc64le` et `osx-arm64` pour LLVM (22.1.8) comme pour Node (26.6.0).
- **PyPI** est maintenu en canal « apporte ton LLVM » : la wheel contient le cœur et les binaires autonomes, les prérequis externes sont déclarés et `doctor` explique comment les obtenir. Un utilisateur pip sans LLVM obtient un outil **partiellement fonctionnel dès la première installation**, ce qui n'est acceptable que parce que `doctor` le dit franchement, avant le run, avec la commande exacte.
- Réserve à documenter dans la recette spack : sans LLVM externe déclaré dans `packages.yaml`, `spack install nunatak` **compilera LLVM depuis les sources**, ce qui prend des heures. `doctor` doit savoir dire « ton LLVM système ferait l'affaire, déclare-le en externe ».

### Version de LLVM et couverture des microarchitectures

- Dépendance déclarée : **`llvm@19:`**. Mesure à l'appui, en interrogeant les tables de microarchitectures de chaque branche : LLVM 17 apporte znver4, sapphirerapids, graniterapids, apple-m1/m2 et neoverse-n1/n2/v1/v2 ; **18** ajoute apple-m3 ; **19** ajoute **znver5, apple-m4, neoverse-v3 et neoverse-n3** ; **20** ajoute diamondrapids.
- **LLVM 17 et 18 sont tolérés, pas refusés** : la symbolisation y est complète, `llvm-symbolizer` étant mature et les notes de version 18 à 22 ne portant que des corrections mineures. Seule l'analyse de boucle se restreint aux microarchitectures que cette version connaît.
- En dessous de 17, ou en l'absence de LLVM : **repli sur le sous-processus système** déjà décidé au ticket 07 (`addr2line` sur Linux, `atos` sur macOS), et pas d'analyse de boucle. Utiliser un LLVM trop ancien « au cas où » serait pire, car on obtiendrait des résultats silencieusement dégradés là où le repli, lui, est déclaré.
- **La règle de sûreté est mécanique** et repose sur le fait que LLVM sait lister les `-mcpu` qu'il connaît : microarchitecture absente de la liste de la version installée, les bornes de cycles sont « indisponible » avec pour raison « installe un LLVM 19 ou plus récent » ; microarchitecture présente, elles sont « estimé ». Sur un nœud Zen 5 équipé de LLVM 18, aucun résultat faux n'est produit, seulement un manque déclaré. C'est cette règle qui rend la tolérance des vieilles versions sûre.

### Deux familles de résultats dans l'analyse statique de boucle

- Ne dépendent **que du désassembleur** : taux et largeur de vectorisation, motif d'accès mémoire, **intensité arithmétique L1**. Ce sont des comptages sur le flux d'instructions.
- Dépendent **du modèle d'ordonnancement** : les bornes de cycles côté ports d'exécution et côté chaîne de dépendances.
- Conséquence qui corrige l'ADR 0004 : **l'intensité arithmétique L1 survit partout où LLVM sait désassembler**, y compris sur les cœurs Apple dont le modèle d'ordonnancement est approximatif. Le sauvetage du roofline sur Apple Silicon ne dépend donc pas de la qualité du modèle. En sens inverse, le désassembleur lui-même vieillit : un binaire compilé avec les extensions les plus récentes (AMX, AVX les plus neuves) n'est pas décodable par un LLVM ancien.
- **L'analyse statique ne produit jamais la Qualité « mesuré »**, quelle que soit la version de LLVM. C'est un modèle, pas une mesure de la machine.

### Veille et montée de version

LLVM publie une majeure **tous les six mois à date prévisible** : 18.1.0 en mars 2024, 19.1.0 en septembre 2024, 20.1.0 en mars 2025, 21.1.0 en août 2025, 22.1.0 en février 2026. La veille se planifie donc au lieu de se subir, et elle doit être **outillée et non déclarative**, sans quoi elle ne survivra pas à la deuxième année.

- Un **job de CI déclenché sur chaque rc et chaque majeure** qui, d'une part, **diffe la liste des `-mcpu`** contre la version précédente et ouvre un ticket listant les microarchitectures nouvellement connues - ce signal déclenche l'ajout au banc de test et la mise à jour de la table de repli théorique du ticket 05 - et d'autre part **rejoue le corpus de non-régression des parseurs** contre les sorties de `llvm-mca` et `llvm-symbolizer` de la nouvelle version.
- Un **corpus de binaires figés** sans lequel ce qui précède ne vaut rien : avec DWARF, sans, strippés, fortement inlinés, vectorisés AVX-512 et SVE, accompagnés des sorties attendues. C'est l'actif le plus durable de cette décision, et il alimentera la stratégie de test que la carte laisse ouverte.
- **Borne supérieure ouverte, fenêtre testée déclarée.** Au-delà, `doctor` **avertit sans refuser** : « LLVM 24 détecté, non validé avec cette version de nunatak ». Si un parseur casse vraiment, il casse bruyamment, pas en silence.
- La même veille couvre **tous les outils orchestrés** (perf, `nsys`, `ncu`, rocprofv3, mpiP, py-spy). Le ticket 04 avait posé le principe des parseurs versionnés par version d'outil détectée sans dire ce qui déclenche leur mise à jour : c'est cette pièce qui manquait.
- **Cadence de release propre**, non alignée sur celle de LLVM.

### Node.js et pi

Le ticket 12 en avait fait des prérequis durs. Ils sont **alignés sur le motif commun** de dégradation fonctionnelle nommée qui régit désormais tout le reste (piles d'appels, LLVM, source, collecteurs). L'architecture le commande : `CONTEXT.md` sépare le Diagnostic déterministe, recalculé, de l'Explication, persistée à part et étiquetée « conseil » ; la production factuelle de l'outil ne dépend en rien du LLM. Un prérequis dur reviendrait à refuser l'installation à un utilisateur sur cluster coupé du réseau, qui ne pourra de toute façon jamais appeler un provider distant, alors que tout le cœur déterministe lui serait utile.

Concrètement : déclarés en dépendances sur conda-forge et spack, donc présents par défaut sur le chemin nominal ; absents ailleurs, ils produisent « Explication indisponible : Node.js ou pi introuvable », annoncé par `doctor`, et le run se déroule.

### Ce que contient la wheel, et sous quelle forme

- Le noyau de calibration et la sonde réseau sont des **exécutables autonomes invoqués en sous-processus**, pas des modules d'extension Python. Trois raisons, dont une qui n'est pas de commodité : c'est le principe « exec + parse, jamais link » du ticket 04 appliqué à nos propres binaires ; la wheel devient `py3-none-<plateforme>`, donc **un artefact par plateforme au lieu d'un par couple (plateforme, version de Python)**, exactement comme `py-spy` dont les wheels sont `py2.py3-none-*` ; et la **Calibration mesurée dans un processus propre** donne une borne supérieure plus juste que la même mesure prise avec l'interpréteur Python résident, son allocateur et son GIL.
- **Versions de Python : le support amont de CPython**, sans politique maison - aujourd'hui 3.11 à 3.14, et chaque version est abandonnée le jour où CPython l'abandonne. Supporter 3.10, qui s'éteint le 31 octobre 2026, reviendrait à naître avec une version déjà morte.
- À écrire noir sur blanc dans la documentation, la confusion étant garantie : **la version de Python qui exécute nunatak n'a rien à voir avec celle de l'application profilée**. Le seuil de 3.12 du ticket 07 porte sur l'interpréteur de l'application (les trampolines perf), pas sur le nôtre.
- **NVIDIA : PTX seul**, pour une base basse. Le pilote compile le PTX à la volée pour l'architecture réellement présente, ce qui couvre gratuitement les GPU postérieurs à la publication de la wheel. Des cubins pour les architectures les plus courantes pourront être ajoutés plus tard si le délai de compilation au premier lancement se révèle gênant.
- **AMD : `gfx90a` (MI200, donc Frontier et LUMI), `gfx942` (MI300, donc El Capitan et le parc en déploiement), `gfx908` (MI100)**. Il n'existe pas d'équivalent du PTX : une cible non listée ne tourne pas du tout. Le reste, notamment les RDNA de station de travail, passe par la recompilation locale. Les **cibles génériques par famille** récemment introduites par ROCm sont à évaluer au moment de l'implémentation, elles réduiraient cette énumération. Cette asymétrie NVIDIA/AMD doit être documentée comme un choix, pas subie comme un oubli, exactement comme l'attribution par ligne indisponible sur AMD au ticket 07.
- **CPU : dispatch d'ISA à l'exécution** (`CPUID` sur x86, `AT_HWCAP` sur ARM). C'est nécessaire et non cosmétique : la Calibration cherche une borne supérieure, et mesurer le pic avec des instructions plus étroites que ce que la machine sait faire produirait un plafond faux portant l'étiquette « mesuré », ce qui est pire qu'un plafond estimé.
- ISA non couverte : **recompilation locale** depuis les sources embarquées, puis **table théorique de microarchitectures** en dernier recours, selon l'échelle déjà fixée au ticket 05.

### La sonde réseau

- Elle se lie à la pile MPI du site, dont les ABI (OpenMPI, MPICH, Intel MPI, Cray MPICH) sont mutuellement incompatibles. **MPI 5.0, approuvé le 5 juin 2025, normalise un ABI**, ce qui rendra un jour la précompilation possible : à surveiller, pas à parier dessus, les implémentations puis les centres mettant des années à suivre.
- Elle est construite **au premier usage, jamais à l'installation** : sur un cluster à modules, le MPI chargé à l'installation n'est presque jamais celui du job, et l'erreur ne se manifesterait qu'à l'exécution, sous forme de symboles manquants ou, pire, de mesures fausses.
- Le binaire est **mis en cache par clé `(implémentation, version, mpicc)`** : un utilisateur qui alterne entre trois modules MPI obtient trois sondes, chacune correcte.
- La construction a lieu de préférence pendant `doctor`, donc typiquement sur un nœud de connexion, certains nœuds de calcul n'ayant pas de compilateur. La **Provenance enregistre contre quelle pile MPI la sonde a été construite** : une analyse réseau dont on ignore la pile sous-jacente n'est pas interprétable.
- Pas de `mpicc` utilisable : **analyse MPI indisponible**, dégradation nommée, annoncée avant le run. Le reste du profilage n'en dépend pas.
- **Le mécanisme couvre aussi mpiP**, retenu comme collecteur MPI principal au ticket 04 : le `LD_PRELOAD` évite de recompiler l'application, pas de compiler mpiP, contrainte que le ticket 04 n'avait pas explicitée. On construit mpiP localement, ou on utilise celui du site s'il existe.

### Les outils externes, en trois catégories

1. **Livrés par nos canaux, en dépendances déclarées** : py-spy, Node.js, pi, LLVM.
2. **Construits localement depuis des sources embarquées** : la sonde réseau et mpiP.
3. **Jamais livrables, fournis par le site** : `nsys` et `ncu` (l'EULA NVIDIA interdit la redistribution), `perf` (lié à la version du noyau), rocprofv3 (vient avec ROCm), LIKWID (GPL-3, et raffinement optionnel depuis le ticket 05).

Pour la troisième catégorie, la seule politique tenable est **détecter, nommer la capacité perdue, indiquer comment le site la fournit** (« `module load cuda` puis relance »). Aucune installation guidée qui téléchargerait quoi que ce soit.

### `doctor`, couture entre l'installation et l'usage

- Il inventorie les trois catégories avec leurs versions, vérifie les permissions (niveau `paranoid` de perf, `ERR_NVGPUCTRPERM`) et inspecte le binaire cible selon le ticket 07 (`-g`, frame pointers, `-lineinfo`, `.dSYM`).
- Deux règles de méthode, tirées de faits vérifiés sur machine : **ne jamais se fier à `xcrun --find`** - sur une machine où `xcode-select` pointe vers un Xcode désinstallé, il déclare absents `dsymutil`, `nm` et `atos` qui sont pourtant dans `/usr/bin` - et **ne jamais se fier au seul `PATH`**, la formule Homebrew `llvm` étant `keg_only` donc jamais liée. `doctor` sonde les chemins et **invoque** les outils.
- Un **sous-ensemble bon marché s'exécute automatiquement au début de `run`** : pas de construction, pas de benchmark, quelques dizaines de millisecondes. Il annonce ce qui sera dégradé **puis continue**. C'est la raison d'être du ticket 07, prévenir avant de brûler une allocation et non après. Le `doctor` complet reste une commande explicite.
- **`--strict`** transforme toute dégradation annoncée en erreur, et `doctor` sait sortir du **JSON**. En CI de performance ou dans une campagne de mesures reproductibles, obtenir en silence un roofline estimé là où on attendait du mesuré est précisément ce qu'on ne veut pas.
