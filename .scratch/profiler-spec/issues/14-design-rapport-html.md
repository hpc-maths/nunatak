# Décision : design du rapport HTML

Type: prototype

## Question

À quoi ressemble le rapport HTML auto-contenu, et quelles vues/interactions offre-t-il, maintenant que le modèle de données (ticket 06) est fixé ?

Le rapport est une mini-app TypeScript embarquée, alimentée par le pivot mesuré (Hotspot/Locus/Mesure/Événement) plus le Diagnostic recalculé et l'Explication LLM. À trancher via /prototype (variations d'UI sur des données d'exemple) : la vue roofline interactive (plafonds, points par Hotspot, qualité mesuré/estimé visible), la timeline (flux d'Événements, MPI par rang), la vue par Hotspot (métriques + source + Explication étiquetée « conseil »), la synthèse des bottlenecks, et comment le déséquilibre de charge entre Loci est rendu. Contrainte : auto-contenu, fonctionne sur cluster sans serveur, sans requête externe.

Note issue du ticket 07 : sept exigences de plus, dont plusieurs sont des vues à part entière. Le **Niveau de résolution** de chaque Hotspot doit être lisible sans être envahissant, et se distinguer visuellement de la Qualité - ce sont deux registres différents (identité contre incertitude). La **vue par Hotspot** doit ventiler les échantillons par frame inline et par ligne, avec les vrais fichiers sources et un extrait de code, et une **vue transverse « temps par frame inline, tous Hotspots confondus »** existe en secondaire. L'**assembleur** (x86, PTX, SASS) est consultable en détail dépliable, jamais dans le prompt du LLM. Le mode **`--no-source`** doit produire un rapport utile sans une ligne de code : numéros de ligne et métriques seuls. La **Provenance** (commit, patch, bibliothèques chargées avec build-id, options de compilation) doit être consultable sans encombrer la vue principale. Et il faut une **vue de comparaison** entre deux Runs (`nunatak compare`), qui montre l'écart par fonction logique inlining compris, porte l'incertitude statistique dans l'écart affiché, et déclare non comparable ce qui l'est.

Note issue du ticket 10 : le rapport doit rendre lisibles trois formes d'incomplétude sans noyer l'utilisateur - la **couverture d'échantillonnage** (quelle fraction des lancements GPU a été instrumentée, quels rangs ont été échantillonnés), l'**agrégat « autres »** qui absorbe les Hotspots sous le plancher statistique, et le fait que certains Loci ne portent que des agrégats par rang, sans aucun Hotspot. S'y ajoute l'affichage de la **rétrogradation motivée** : montrer non seulement qu'une valeur est « estimé », mais pourquoi.
