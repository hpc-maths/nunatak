# Décision : design du rapport HTML

Type: prototype
Status: resolved

## Question

À quoi ressemble le rapport HTML auto-contenu, et quelles vues/interactions offre-t-il, maintenant que le modèle de données (ticket 06) est fixé ?

Le rapport est une mini-app TypeScript embarquée, alimentée par le pivot mesuré (Hotspot/Locus/Mesure/Événement) plus le Diagnostic recalculé et l'Explication LLM. À trancher via /prototype (variations d'UI sur des données d'exemple) : la vue roofline interactive (plafonds, points par Hotspot, qualité mesuré/estimé visible), la timeline (flux d'Événements, MPI par rang), la vue par Hotspot (métriques + source + Explication étiquetée « conseil »), la synthèse des bottlenecks, et comment le déséquilibre de charge entre Loci est rendu. Contrainte : auto-contenu, fonctionne sur cluster sans serveur, sans requête externe.

Note issue du ticket 07 : sept exigences de plus, dont plusieurs sont des vues à part entière. Le **Niveau de résolution** de chaque Hotspot doit être lisible sans être envahissant, et se distinguer visuellement de la Qualité - ce sont deux registres différents (identité contre incertitude). La **vue par Hotspot** doit ventiler les échantillons par frame inline et par ligne, avec les vrais fichiers sources et un extrait de code, et une **vue transverse « temps par frame inline, tous Hotspots confondus »** existe en secondaire. L'**assembleur** (x86, PTX, SASS) est consultable en détail dépliable, jamais dans le prompt du LLM. Le mode **`--no-source`** doit produire un rapport utile sans une ligne de code : numéros de ligne et métriques seuls. La **Provenance** (commit, patch, bibliothèques chargées avec build-id, options de compilation) doit être consultable sans encombrer la vue principale. Et il faut une **vue de comparaison** entre deux Runs (`nunatak compare`), qui montre l'écart par fonction logique inlining compris, porte l'incertitude statistique dans l'écart affiché, et déclare non comparable ce qui l'est.

Note issue du ticket 10 : le rapport doit rendre lisibles trois formes d'incomplétude sans noyer l'utilisateur - la **couverture d'échantillonnage** (quelle fraction des lancements GPU a été instrumentée, quels rangs ont été échantillonnés), l'**agrégat « autres »** qui absorbe les Hotspots sous le plancher statistique, et le fait que certains Loci ne portent que des agrégats par rang, sans aucun Hotspot. S'y ajoute l'affichage de la **rétrogradation motivée** : montrer non seulement qu'une valeur est « estimé », mais pourquoi.

## Answer

Décision prise en session /prototype ; arbitrage complet dans `docs/adr/0006-design-rapport-html.md`. Prototypes sur la branche `prototype/rapport-html` (commit `6c5ec2f`) : trois variantes commutables plus la structure retenue.

**Trois niveaux de lecture, et le roofline au troisième.** Une **synthèse rédigée** ouvre le rapport (constats classés par part du temps, chacun avec ses preuves chiffrées, et une section « ce que ce rapport ne dit pas ») ; un **inventaire dense** liste tous les Hotspots, triable et filtrable ; le **détail d'un Hotspot** contient le roofline.

**Le roofline n'est pas la porte d'entrée mais la récompense du forage.** Ce déplacement corrige un défaut de fond : un roofline global mélangerait CPU et GPU, dont les Plafonds n'ont rien à voir. Contextualisé sur un Hotspot, l'appareil devient implicite et le graphe est correct par construction - Plafonds, Hotspot en évidence, autres Hotspots du même appareil en points pâles pour l'échelle.

**Les vues se substituent, jamais côte à côte.** Une première tentative mettait l'inventaire et le détail en deux volets : côte à côte ne réduit pas le défilement, cela rétrécit les deux. La cause réelle était le détail empilé sur une colonne ; il se répartit désormais sur **deux colonnes** et tient à l'écran.

**Vocabulaire visuel de l'incertitude : deux registres, deux canaux.** La **Qualité** est portée par la couleur et la forme (plein / hachuré / pointillé), partout de la même façon - pastille, barre de part du temps, point du roofline. Le **Niveau de résolution** est porté par une étiquette texte neutre, sans couleur, parce qu'il ne dit pas la même chose. La **rétrogradation motivée** affiche sa raison, pas seulement son étiquette.

**L'incomplétude est rassemblée, pas dispersée** : une section « ce que ce rapport ne dit pas » en fin de synthèse, un Hotspot non plaçable qui explique pourquoi **à l'endroit où le roofline était attendu**, « indisponible » jamais confondu avec zéro, et la couverture d'échantillonnage annoncée en tête.

**Modes et tiroirs** : `--no-source` garde les numéros de ligne et la distribution des échantillons en remplaçant le code par des points de suspension ; la Provenance est un tiroir dépliable ; l'assembleur un bloc dépliable jamais envoyé au modèle. La vue de comparaison (`nunatak compare`) suit la même structure à trois niveaux mais n'a pas été prototypée.

**Trois défauts que seul le rendu à l'écran a révélés** : le premier graphe n'était pas un roofline (les diagonales mémoire traversaient le plafond de calcul au lieu de s'arrêter au point de rupture) ; un graphe en largeur fluide emporte sa typographie et doit être borné à sa taille naturelle ; les étiquettes croisent nécessairement des lignes en plan log-log et ont besoin d'un halo.
