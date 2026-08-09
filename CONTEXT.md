# Profiler - modèle de domaine

Glossaire du profiler : librairie de profiling zéro-instrumentation qui place les unités de calcul sur un roofline, diagnostique les bottlenecks CPU/GPU/mémoire/réseau, et les fait expliquer par un LLM. Ce fichier est un glossaire, pas une spec : il fixe le vocabulaire, jamais l'implémentation.

## Language

**Hotspot**:
L'unité atomique d'analyse - la chose qu'on place sur le roofline, qu'on diagnostique et qu'on donne au LLM. C'est une fonction sur CPU (symbole DWARF), un kernel groupé par nom sur GPU, une frame sur Python. Découvrable sans instrumentation par tous les collecteurs. Il porte deux identités de portées différentes : une identité **physique** `(build-id ou LC_UUID du module, offset)`, qui agrège les échantillons à l'intérieur d'un Run et n'existe que pour le natif ; et une identité **logique** `(module, nom démanglé, fichier source)`, qui affiche, alimente le LLM, permet la comparaison entre Runs, et se transpose au GPU comme à Python. Les lignes et la chaîne d'inlining sont un détail interne au Hotspot, jamais une unité d'analyse.
_Avoid_: kernel (ambigu : réservé au sens GPU), région, fonction (trop spécifique CPU), symbole

**Locus**:
Un point dans la topologie d'exécution où un Hotspot est observé, structuré en niveaux : nœud > rang MPI > thread pour le CPU, nœud > device GPU > stream pour le GPU. C'est l'axe « où » du profiling.
_Avoid_: rang (c'est un niveau du Locus, pas le Locus), place, worker

**Mesure**:
Une valeur attachée à un couple (Hotspot, Locus) : le trafic DRAM de la fonction `foo` sur le rang 3 thread 2. C'est le grain élémentaire des données. L'agrégation entre loci (somme, moyenne, min/max, déséquilibre) est calculée à la demande, jamais stockée. Une Mesure transporte aussi de quoi juger de sa propre solidité : son nombre d'échantillons et l'erreur relative qui en découle, son taux de couverture quand les compteurs ont été multiplexés, et sa Passe d'origine.
_Avoid_: valeur, point de données, échantillon (l'échantillon est une source de mesures, pas la mesure)

**Compteur brut**:
Ce qu'un collecteur rapporte directement, sans transformation : `FP_ARITH_INST_RETIRED.SCALAR_DOUBLE`, `CAS_COUNT`, `dram__bytes.sum`. Une Mesure d'un Compteur brut est toujours de qualité « mesuré » (ou « indisponible » si le compteur n'existe pas sur la microarchitecture).
_Avoid_: événement, hardware counter, raw metric

**Métrique dérivée**:
Une grandeur calculée à partir de Compteurs bruts via une Formule : intensité arithmétique, GFLOP/s, taux de hit L2, bande passante. Elle mémorise ses compteurs sources et sa formule (son Linéage).
_Avoid_: métrique (préciser toujours brut ou dérivé), KPI, indicateur

**Intensité arithmétique**:
L'axe horizontal du roofline, en FLOP par octet. Il en existe **deux, jamais interchangeables**, et les confondre est une faute. L'**intensité DRAM** rapporte les FLOPs au trafic réellement échangé avec la mémoire principale : elle est mesurée aux Compteurs bruts, elle dépend de la réutilisation en cache, et c'est celle du roofline classique. L'**intensité L1** rapporte les FLOPs aux octets demandés par le flux d'instructions : elle est dérivée de l'Analyse statique de boucle, elle ne dit rien de la réutilisation en cache, et elle existe même là où aucun compteur n'est disponible - c'est ce qui rend un roofline possible sur Apple Silicon. Toute mention doit préciser laquelle.
_Avoid_: intensité arithmétique tout court (toujours préciser DRAM ou L1), AI, intensité opérationnelle

**Analyse statique de boucle**:
L'examen du binaire désassemblé d'une boucle interne chaude, sans l'exécuter : taux et largeur de vectorisation, motif d'accès mémoire, bornes de cycles côté ports d'exécution et côté chaîne de dépendances, intensité arithmétique L1. Elle produit des **faits**, pas des Mesures : ils n'ont ni Locus ni nombre d'échantillons, et ne viennent d'aucun collecteur. Elle porte une Qualité, qui dépend de la finesse du modèle d'ordonnancement de la microarchitecture visée.
_Avoid_: analyse de code, CQA, MAQAO (l'outil est écarté, les cas d'usage sont repris), analyse dynamique

**Qualité**:
L'étiquette de confiance d'une Mesure ou d'un Plafond : « mesuré », « estimé » ou « indisponible ». Pour une Métrique dérivée, la Qualité se propage automatiquement le long du Linéage : elle vaut la pire de ses entrées (des FLOPs estimés donnent une intensité arithmétique estimée). Rend explicite pourquoi un chiffre est incertain - imposé par macOS (pas de compteur FLOPs) et les microarchitectures aux compteurs non fiables.
_Avoid_: confiance, fiabilité, précision

**Rétrogradation motivée**:
Le mécanisme par lequel une valeur nominalement mesurée retombe à la Qualité « estimé », accompagnée d'une raison lisible. C'est la façon dont le système reste honnête sans multiplier les niveaux de Qualité : les trois états ne bougent pas, seule la raison varie. Les situations qui la déclenchent aujourd'hui : Calibration réalisée dans des conditions polluées, compteurs multiplexés sous le seuil de couverture, Hotspot sous le plancher statistique, passes incohérentes en mode multi-passes, distribution par ligne issue d'une table de lignes bruitée par l'optimisation, bornes d'Analyse statique de boucle sur une microarchitecture au modèle d'ordonnancement approximatif. Toute approximation nouvelle doit s'y rattacher plutôt qu'inventer son propre vocabulaire. Elle ne couvre en revanche **pas** les deux cas voisins que sont l'échec d'attribution, qui relève du Niveau de résolution, et l'invalidité, qui se refuse au lieu de se rétrograder.
_Avoid_: dégradation (réservé à la dégradation fonctionnelle quand un collecteur manque), avertissement, warning

**Niveau de résolution**:
Jusqu'où l'attribution d'un Hotspot a pu descendre : « ligne », « fonction », « symbole » ou « non résolu ». C'est un attribut du Hotspot, **distinct de la Qualité** : quand l'attribution échoue, la Mesure reste exacte - ce temps a bien été passé à cette adresse - et c'est l'identité qui se dégrade, pas la valeur. Il conditionne ce que voit l'utilisateur et ce qui part au LLM : sans source, pas d'Explication.
_Avoid_: qualité de symbolisation, précision d'attribution, confiance

**Passe**:
Une exécution de l'application au sein d'un même Run. Le mode nominal n'en compte qu'une ; le mode multi-passes en enchaîne plusieurs, avec des groupes de compteurs disjoints, pour éviter le multiplexing. Un Run reste une invocation de `nunatak run`, quel que soit le nombre de Passes, et chaque Mesure sait de quelle Passe elle vient.
_Avoid_: run (réservé au conteneur), exécution, itération, replay (le replay est le rejeu d'un kernel par ncu, à l'intérieur d'une Passe)

**Événement**:
Un fait horodaté avec une durée : un lancement de kernel GPU, un appel MPI avec son temps d'attente et son volume. Le flux d'Événements alimente la timeline du rapport et l'analyse réseau ; il est distinct des Mesures agrégées (qui, elles, alimentent le roofline et le diagnostic). Un collecteur remplit les Mesures, les Événements, ou les deux.
_Avoid_: span, trace, sample, record

**Run**:
Une session de profiling - une invocation de `nunatak run -- ...`. C'est le conteneur persisté du pivot mesuré : ses Hotspots, Loci, Mesures et Événements, plus une référence à la Machine et sa Provenance. Ne contient aucune sortie d'analyse (recalculées) ni Explication (persistée à part).
_Avoid_: session, profil, trace, expérience

**Provenance**:
Ce qui permet d'expliquer un Run sans le rejouer : l'identité du code (commit, arbre propre ou sale, patch des modifications non commitées), les dépendances à l'exécution (bibliothèques réellement chargées, avec leur build-id), et celles de la construction (modules d'environnement, options de compilation lues dans le binaire). Vit dans le manifeste du Run, jamais dans le pivot mesuré. Elle est best-effort et ne bloque jamais un Run, et elle est **descriptive et non certifiante** : elle enregistre ce qu'elle observe et ne garantit pas que le binaire dérive du commit.
_Avoid_: métadonnées, environnement, reproductibilité (elle ne la garantit pas), contexte

**Machine**:
Le matériel sur lequel un Run s'exécute, porteur des Plafonds du roofline. Entité distincte du Run, partagée et mise en cache entre Runs. Son identité n'est pas un nœud mais un couple matériel + forme d'allocation : deux jobs recevant des parts différentes du même nœud sont deux Machines, et mille nœuds identiques d'un cluster n'en sont qu'une. Chaque Run embarque un instantané complet de sa Machine.
_Avoid_: nœud (le nœud est un niveau de Locus), cible, hôte

**Plafond**:
Une borne supérieure de performance de la Machine, atteignable en pratique : pic FLOP/s par précision, bande passante par niveau de la hiérarchie mémoire, bande passante réseau. C'est le toit du roofline. Comme une Mesure, un Plafond porte une Qualité (« mesuré » quand il vient d'une Calibration réussie, « estimé » quand il est calculé théoriquement ou mesuré dans des conditions suspectes). Il vaut pour un périmètre donné - celui de l'allocation - et se compare donc à des Mesures agrégées sur ce même périmètre.
_Avoid_: pic, peak, roofline (le roofline est le modèle, pas la valeur), limite

**Calibration**:
L'opération qui produit les Plafonds d'une Machine en exécutant des microbenchmarks sur la cible. Déclenchée une fois par Machine, mise en cache, jamais rejouée sans raison. Un Plafond est le maximum de ses répétitions, jamais leur moyenne : on cherche une borne supérieure.
_Avoid_: benchmark (le benchmark est l'outil, la Calibration est l'opération), mesure (réservé au pivot mesuré), profilage machine

**Diagnostic**:
Le verdict déterministe et reproductible produit par le moteur d'analyse pour un Hotspot : son Placement roofline (intensité arithmétique, performance atteinte vs plafonds) et sa classification (memory-bound, core-bound, latency-bound, déséquilibre...). Recalculé à la demande depuis le pivot mesuré + la Machine, jamais persisté. C'est ce qui constitue les « faits » donnés au LLM.
_Avoid_: verdict, analyse, résultat, bottleneck (le bottleneck est une conclusion du Diagnostic)

**Explication**:
Le conseil généré par le LLM à partir du Diagnostic + du source du Hotspot. Non reproductible, persistée séparément du pivot mesuré et toujours étiquetée « conseil » - jamais mélangée aux faits déterministes. Peut être régénérée sans reprofiler.
_Avoid_: conseil, recommandation, avis, sortie LLM
