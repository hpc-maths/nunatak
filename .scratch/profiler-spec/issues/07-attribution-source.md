# Décision : attribution kernel vers code source

Type: grilling
Blocked by: 04
Status: resolved

## Question

Comment remonter d'un kernel/hotspot mesuré au code source à montrer au LLM et à l'utilisateur, pour chaque famille de langages de la v1 ?

À trancher : exploitation DWARF pour les compilés (que faire des binaires sans -g ? inlining ?), chemin Python (py-spy / perf-trampoline), kernels GPU (mapping nom de kernel CUDA/HIP vers source, PTX/SASS utile au LLM ?), et la politique quand le source est introuvable (analyse au niveau assembleur ? dégradation ?).

Note issue du ticket 10 : l'attribution doit couvrir **deux natures de source** - des échantillons avec pile d'appels côté Linux (échantillonnage déclenché par événement) et des échantillons purement temporels côté macOS (`xctrace` ou `/usr/bin/sample`) - et n'a **rien à attribuer** pour la couche de comptage, qui ne produit que des agrégats par rang sans Hotspot. À trancher ici aussi : ce que l'attribution doit garantir pour rester stable d'une Passe à l'autre en mode multi-passes (ASLR, réordonnancement, binaires recompilés entre passes).

## Answer

Décision prise en session /grilling ; arbitrage complet dans `docs/adr/0004-attribution-source.md`.

**Double identité du Hotspot.** Physique `(build-id | LC_UUID, offset)` pour agréger dans un Run et valider les fusions ; logique `(module, nom démanglé, fichier source)` pour afficher, alimenter le LLM et comparer entre Runs. La ligne de déclaration est un attribut, jamais une clé (une édition en tête de fichier casserait toute comparaison). Aucune adresse absolue persistée : ASLR et réordonnancement tombent par construction. L'identité logique se transpose au GPU et à Python ; seul le natif a une identité physique.

**Le Hotspot reste la fonction physique**, lignes et chaîne d'inlining conservées en détail interne. Vue transverse « temps par frame inline » en secondaire, qui est la seule vue stable à travers une recompilation. Les piles d'appels (`lbr` > `fp` > rien, `dwarf` opt-in seulement) rattachent les feuilles de bibliothèque au code utilisateur mais n'entrent pas dans l'identité.

**Niveau de résolution** (ligne / fonction / symbole / non résolu) comme attribut du Hotspot, **distinct de la Qualité** : quand l'attribution échoue, la Mesure reste exacte, c'est l'identité qui se dégrade. **Règle d'étendue** : jamais d'attribution dans un trou entre symboles ELF. `doctor` réclame `-g`, `-fno-omit-frame-pointer`, `-lineinfo`, `dsymutil` **avant** de brûler une allocation.

**Symboliseur permissif embarqué dans la wheel** (LLVM ou `gimli`/`addr2line`), sous-processus système en repli (`addr2line` GPL et `atos` Xcode : exécutables, jamais redistribuables).

**Python** : `PYTHONPERFSUPPORT` posé au lancement, maps `/tmp/perf-<pid>.map` rapatriées avant l'épilogue du job ; frames d'interpréteur repliées sur la frame Python la plus interne ; extensions natives = Hotspots natifs ; py-spy = compteurs « indisponible ».

**macOS** : `LC_UUID`, DWARF hors du binaire (`.dSYM` ou carte de debug vers les `.o`, donc `make clean` détruit l'attribution ligne) ; `doctor` invoque réellement `xctrace`, dont le shim existe sans Xcode ; piles gratuites et fiables ; `xctrace` donne l'échelle complète, `/usr/bin/sample` plafonne à « fonction » avec l'attribution d'Apple héritée et déclarée. Cadrage : macOS sert la boucle de développement courte, pas le verdict de référence, et on ne cherche pas à rivaliser avec Instruments.

**GPU** : `-lineinfo` recommandé non requis, annoncé par `doctor` ; ligne « indisponible » sur AMD en v1 ; groupement par nom, configuration de lancement en détail interne ; site d'appel hôte échantillonné et borné.

**Le LLM ne reçoit jamais d'assembleur brut** (x86, PTX, SASS) : ce serait lui demander de diagnostiquer. Il reçoit source, distribution par ligne, Diagnostic et faits dérivés déterministes ; l'assembleur reste consultable dans le rapport. Rapports d'optimisation du compilateur acceptés s'ils sont déjà présents et vérifiables, jamais provoqués. **MAQAO écarté mais ses cas d'usage repris** par une analyse statique de boucle maison bâtie sur le LLVM déjà embarqué (vectorisation, motif d'accès, bornes ports et dépendances, intensité arithmétique statique) - grandeur **distincte** de l'intensité mesurée, et voie de consolidation du roofline estimé sur Apple Silicon.

**Source** : recherche puis `--source-map`, refus en cas d'ambiguïté ; empreinte MD5 de DWARF 5 comme garde-fou de péremption ; extraits seuls embarqués ; deux commutateurs distincts (`--no-source` pour le rapport, accord explicite et mémorisé pour un provider LLM distant). **Pas de source, pas d'Explication.**

**Provenance** comme nouvel attribut du Run : commit et patch borné soumis à `--no-source`, bibliothèques chargées avec build-id (gratuit), `module list`/Spack/conda et options de compilation lues dans `DW_AT_producer`. Best-effort, jamais bloquante, descriptive et non certifiante.

**Multi-passes** : une recompilation entre Passes est une invalidité, pas une incertitude - **refus de fusion au niveau du module**, pas de rétrogradation. **Comparer deux versions = deux Runs** : `nunatak compare runA runB` minimal en v1 (terminal + rapport de diff, sans historique), unité de comparaison = la fonction logique inlining compris, garde-fous Machine/rangs/entrées identiques et incertitude statistique portée dans l'écart.
