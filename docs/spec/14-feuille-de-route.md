# 14 - Feuille de route et angles morts

## Ordre de construction suggéré

Cet ordre découle des dépendances réelles entre chapitres, pas d'une préférence. Chaque étape produit quelque chose d'utilisable.

**1. Le socle mesurable.** Pivot Parquet et manifeste (02), squelette CLI avec `run` et `doctor` (11), un seul adaptateur - `perf` sur Linux x86 - et son parseur, plus le mécanisme d'enregistrement du corpus (13). À la fin de cette étape, on capture de vraies sorties et tout le reste devient testable sans matériel.

**2. L'attribution.** Symbolisation, règle d'étendue, chaînes d'inlining, résolution et vérification du source (06). C'est le composant le plus dense et tout dépend de lui. À la fin, on sait dire où part le temps.

**3. Machine et roofline.** Noyau de calibration et dispatch d'ISA (07), moteur d'analyse déterministe et enveloppe roofline (08). À la fin, le produit a sa proposition de valeur.

**4. Le rendu.** Résumé terminal puis rapport HTML (10). À la fin, il est montrable.

**5. L'échelle et le distribué.** Deux couches de collecte, rapatriement multi-nœuds, mpiP et sonde réseau (05, 12).

**6. Les autres plateformes.** GPU NVIDIA, puis macOS, puis GPU AMD - dans cet ordre de couverture décroissante.

**7. L'Explication** (09), en dernier parce qu'elle ne dépend de rien et que rien ne dépend d'elle.

**8. `compare`** (10, 11), qui suppose deux Runs comparables donc tout le reste stable.

L'analyse statique de boucle (08) peut s'insérer après l'étape 3 ; c'est la seule brique dont le périmètre peut être réduit sans casser le reste.

## Le tout premier jalon

Un jalon qui vaut la peine d'être visé explicitement : **`nunatak run -- ./mon_binaire` sur une station Linux x86, produisant un rapport avec un roofline mesuré et des Hotspots attribués à la ligne**. Il traverse les étapes 1 à 4 sans toucher au distribué, au GPU ni au modèle de langage, et il valide l'essentiel de l'architecture.

## Angles morts connus

**L'équivalent macOS des jeux d'événements par microarchitecture.** LIKWID fournit ailleurs des jeux d'événements et des groupes de métriques validés par microarchitecture ; rien d'équivalent n'existe sur Apple Silicon. Les `.plist` de `/usr/share/kpep` sont la matière première identifiée, mais aucune décision n'a été prise. Portée réelle limitée : le chemin macOS nominal est l'échantillonnage temporel sans compteurs (05), et le volet plafonds est couvert par le noyau de calibration (07). Cet angle mort ne bloque donc que le backend kperf expert.

**La vue de comparaison n'a pas été prototypée** (10). Sa structure est fixée par analogie avec le rapport, son détail reste à établir.

**Les cibles génériques ROCm** (12) sont à évaluer : elles réduiraient l'énumération des cibles `gfx`.

## Ce que la v2 pourrait apporter

Ces pistes ont été identifiées en chemin et écartées de la v1 sans que l'architecture ne les empêche :

- **historique et comparaison de plus de deux Runs.** Le socle existe déjà : identité logique stable, Provenance complète, `compare` fonctionnel ;
- **éclatement d'un Hotspot par contexte d'appel.** Les piles sont persistées, il suffirait de les exploiter (06) ;
- **cubins précompilés côté NVIDIA** si le délai de compilation PTX au premier lancement se révèle gênant (12) ;
- **« gain estimé si la boucle était vectorisée »** (08), qui suppose de modéliser une transformation ;
- **plateformes reportées** : GPU Intel, NCCL/RCCL, Dask, `torch.distributed`, Julia, Windows.

## Critère de fin

La spec est tenue si un développeur peut lancer nunatak sur son application sans la modifier, et obtenir un rapport qui lui dit où part son temps, contre quel plafond il bute, **et dans quelle mesure il peut croire ce qu'il lit**.

Ce dernier point n'est pas un ornement : c'est ce qui distingue ce produit, et c'est ce que le site rend mécanique : [comment lire ce que nunatak dit](../guide/reading-what-nunatak-tells-you.md).
