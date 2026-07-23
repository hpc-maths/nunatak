# Profiler - modèle de domaine

Glossaire du profiler : librairie de profiling zéro-instrumentation qui place les unités de calcul sur un roofline, diagnostique les bottlenecks CPU/GPU/mémoire/réseau, et les fait expliquer par un LLM. Ce fichier est un glossaire, pas une spec : il fixe le vocabulaire, jamais l'implémentation.

## Language

**Hotspot**:
L'unité atomique d'analyse - la chose qu'on place sur le roofline, qu'on diagnostique et qu'on donne au LLM. C'est une fonction sur CPU (symbole DWARF), un kernel groupé par nom sur GPU, une frame sur Python. Découvrable sans instrumentation par tous les collecteurs.
_Avoid_: kernel (ambigu : réservé au sens GPU), région, fonction (trop spécifique CPU), symbole

**Locus**:
Un point dans la topologie d'exécution où un Hotspot est observé, structuré en niveaux : nœud > rang MPI > thread pour le CPU, nœud > device GPU > stream pour le GPU. C'est l'axe « où » du profiling.
_Avoid_: rang (c'est un niveau du Locus, pas le Locus), place, worker

**Mesure**:
Une valeur attachée à un couple (Hotspot, Locus) : le trafic DRAM de la fonction `foo` sur le rang 3 thread 2. C'est le grain élémentaire des données. L'agrégation entre loci (somme, moyenne, min/max, déséquilibre) est calculée à la demande, jamais stockée.
_Avoid_: valeur, point de données, échantillon (l'échantillon est une source de mesures, pas la mesure)

**Compteur brut**:
Ce qu'un collecteur rapporte directement, sans transformation : `FP_ARITH_INST_RETIRED.SCALAR_DOUBLE`, `CAS_COUNT`, `dram__bytes.sum`. Une Mesure d'un Compteur brut est toujours de qualité « mesuré » (ou « indisponible » si le compteur n'existe pas sur la microarchitecture).
_Avoid_: événement, hardware counter, raw metric

**Métrique dérivée**:
Une grandeur calculée à partir de Compteurs bruts via une Formule : intensité arithmétique, GFLOP/s, taux de hit L2, bande passante. Elle mémorise ses compteurs sources et sa formule (son Linéage).
_Avoid_: métrique (préciser toujours brut ou dérivé), KPI, indicateur

**Qualité**:
L'étiquette de confiance d'une Mesure : « mesuré », « estimé » ou « indisponible ». Pour une Métrique dérivée, la Qualité se propage automatiquement le long du Linéage : elle vaut la pire de ses entrées (des FLOPs estimés donnent une intensité arithmétique estimée). Rend explicite pourquoi un chiffre est incertain - imposé par macOS (pas de compteur FLOPs) et les microarchitectures aux compteurs non fiables.
_Avoid_: confiance, fiabilité, précision

**Événement**:
Un fait horodaté avec une durée : un lancement de kernel GPU, un appel MPI avec son temps d'attente et son volume. Le flux d'Événements alimente la timeline du rapport et l'analyse réseau ; il est distinct des Mesures agrégées (qui, elles, alimentent le roofline et le diagnostic). Un collecteur remplit les Mesures, les Événements, ou les deux.
_Avoid_: span, trace, sample, record

**Run**:
Une session de profiling - une invocation de `profiler run -- ...`. C'est le conteneur persisté du pivot mesuré : ses Hotspots, Loci, Mesures et Événements, plus une référence à la Machine. Ne contient aucune sortie d'analyse (recalculées) ni Explication (persistée à part).
_Avoid_: session, profil, trace, expérience

**Machine**:
Le matériel sur lequel un Run s'exécute, porteur des plafonds du roofline (pic FLOP/s par précision, bandes passantes par niveau, bande passante réseau). Entité distincte du Run, partagée et mise en cache entre Runs. Comment ses plafonds sont obtenus relève d'une autre décision (caractérisation machine).
_Avoid_: nœud (le nœud est un niveau de Locus), cible, hôte

**Diagnostic**:
Le verdict déterministe et reproductible produit par le moteur d'analyse pour un Hotspot : son Placement roofline (intensité arithmétique, performance atteinte vs plafonds) et sa classification (memory-bound, core-bound, latency-bound, déséquilibre...). Recalculé à la demande depuis le pivot mesuré + la Machine, jamais persisté. C'est ce qui constitue les « faits » donnés au LLM.
_Avoid_: verdict, analyse, résultat, bottleneck (le bottleneck est une conclusion du Diagnostic)

**Explication**:
Le conseil généré par le LLM à partir du Diagnostic + du source du Hotspot. Non reproductible, persistée séparément du pivot mesuré et toujours étiquetée « conseil » - jamais mélangée aux faits déterministes. Peut être régénérée sans reprofiler.
_Avoid_: conseil, recommandation, avis, sortie LLM
