# Rapport HTML : trois niveaux de lecture, et le roofline au troisième

## Contexte et décision

Le rapport est le seul endroit où l'utilisateur rencontre l'ensemble du travail : le pivot mesuré du ticket 06, le Diagnostic déterministe, l'Explication du LLM, et toutes les formes d'incomplétude accumulées aux tickets 07, 10 et 13. La question n'était pas de savoir quelles vues offrir - la liste était connue - mais **par quoi le rapport commence**, puisque ce choix commande tout le reste.

Trois variantes ont été construites sur un même jeu de données et comparées à l'écran (branche `prototype/rapport-html`, commit `6c5ec2f`) : le roofline comme porte d'entrée, une synthèse rédigée, un inventaire dense. La décision retenue **n'est aucune des trois** mais leur composition, en trois niveaux de lecture :

1. **Une synthèse rédigée** ouvre le rapport : des constats en langage naturel, classés par part du temps, chacun assorti de ses preuves chiffrées. Elle se termine par une section **« ce que ce rapport ne dit pas »**.
2. **Un inventaire dense** liste tous les Hotspots, triable et filtrable, avec la Qualité et le Niveau de résolution en colonnes propres.
3. **Le détail d'un Hotspot**, ouvert depuis l'un ou l'autre, et **c'est là que vit le roofline**.

**Le roofline n'est donc pas la porte d'entrée, il est la récompense du forage.** Ce déplacement, qui semblait cosmétique, corrige un défaut de fond : un roofline global doit mélanger CPU et GPU, dont les Plafonds n'ont rien à voir, ou imposer un sélecteur d'appareil. Contextualisé sur un Hotspot, l'appareil devient implicite et le graphe est **correct par construction**. Il montre les Plafonds, le Hotspot sélectionné en évidence, et les autres Hotspots du même appareil en points pâles pour l'échelle.

## Options considérées

- **Le roofline en porte d'entrée** (variante A) : c'est le geste attendu d'un outil de roofline, écarté parce qu'il oblige à répondre « et tout ce qui n'a pas d'intensité arithmétique ? » par un rail latéral, et parce qu'il mélange deux jeux de Plafonds ou impose un sélecteur.
- **La synthèse seule** (variante B) : la plus lisible, écartée seule parce qu'un utilisateur qui cherche un Hotspot précis n'a aucun moyen de le trouver.
- **L'inventaire seul** (variante C) : le plus complet, écarté seul parce qu'il ne dit pas par où commencer, ce que l'utilisateur vient précisément chercher.
- **Inventaire et détail côte à côte**, en deux volets : essayé, puis abandonné après examen à l'écran. Côte à côte ne réduit pas le défilement, cela **rétrécit les deux** : la table perd ses colonnes et le détail s'allonge. La cause réelle du défilement n'était pas la mise en page de la page, mais le détail empilé sur une seule colonne.
- **Le détail en superposition** (tiroir ou modale) : écarté au profit de la substitution, qui reste imprimable, n'introduit pas de piège de défilement et ne demande aucune gestion de plan.
- **Onglets dans le détail** (roofline / source / faits) : écartés une fois le détail passé sur deux colonnes, ils devenaient une navigation de plus pour un contenu qui tient désormais à l'écran.

## Conséquences

### La structure

- **Les trois niveaux se substituent, ils ne cohabitent jamais.** L'inventaire et le détail occupent la même zone ; on n'y défile que dans un seul contenu à la fois. Le retour se fait par un bouton explicite et par `Échap`.
- **Le détail se répartit sur deux colonnes** dès qu'il en a la place : à gauche le roofline, les métriques, les faits déterministes et l'Explication ; à droite le source annoté, la ventilation par frame inline et l'assembleur dépliable. C'est ce qui divise sa hauteur par deux et lui permet de tenir à l'écran.
- Chaque constat de la synthèse porte un accès direct vers le Hotspot concerné et son roofline. La synthèse ne contient **aucun graphe** : elle affirme et cite ses chiffres, le graphe est au niveau suivant.
- Toutes les zones sont calées sur une même mesure. Une table qui s'étale sur toute la largeur d'un grand écran sépare le nom de ses chiffres et casse la lecture ; l'espace ainsi récupéré porte une **barre de part du temps**, qui transforme un vide en information.

### Le vocabulaire visuel de l'incertitude

C'est le cœur de ce que le rapport doit rendre lisible, et il repose sur une règle simple : **deux registres, deux canaux visuels, jamais confondus**.

- **La Qualité est portée par la couleur et la forme** : « mesuré » en plein, « estimé » en hachuré, « indisponible » en contour pointillé. Le même codage vaut partout - la pastille dans une table, la barre de part du temps, le point sur le roofline. Un Hotspot estimé y est un cercle pointillé, un Hotspot mesuré un disque plein.
- **Le Niveau de résolution est porté par une étiquette texte neutre** (ligne, fonction, symbole, non résolu), sans couleur. Il ne dit pas la même chose que la Qualité et ne doit pas lui ressembler : quand l'attribution échoue, la Mesure reste exacte, c'est l'identité qui se dégrade.
- **La rétrogradation motivée affiche sa raison**, pas seulement son étiquette : « rétrogradé en estimé : compteurs multiplexés, couverture 63 % sous le seuil de 80 % ». L'étiquette sans la raison ne sert à rien.

### Rendre l'incomplétude lisible sans noyer l'utilisateur

- **Une section « ce que ce rapport ne dit pas »** clôt la synthèse et rassemble ce qui manque : le temps non attribuable, l'agrégat « autres » et son plancher statistique, les Plafonds estimés, les kernels sans `-lineinfo`, et les rangs non échantillonnés. Rassembler ces aveux en un endroit nommé les rend lisibles ; les disperser en notes de bas de page les rendrait invisibles.
- **Un Hotspot qui ne peut pas être placé sur le roofline le dit à l'endroit où on l'attend.** Quand l'utilisateur ouvre un Hotspot non résolu ou l'agrégat « autres », le graphe est **remplacé par un encadré qui explique pourquoi**, au lieu de disparaître en silence ou d'afficher un graphe vide. C'est la reprise, mieux placée, du rail « hors du roofline » de la variante A.
- **Une grandeur absente s'écrit « indisponible », jamais zéro ni une case vide sans explication.** La table le rappelle explicitement : une colonne vide signifie que la grandeur est indisponible pour ce Hotspot, pas qu'elle vaut zéro.
- La **couverture d'échantillonnage** (quels rangs, quelle fraction des lancements GPU, quel taux de multiplexage) est énoncée en tête de synthèse, pas reléguée en annexe.
- L'**Explication du LLM** est toujours dans un cadre distinct, étiqueté « conseil, généré par un modèle, non reproductible ». Quand elle est absente, le rapport dit **pourquoi** : pas de source, sous le plancher statistique, Hotspot non résolu.

### Les modes et les tiroirs

- **`--no-source`** conserve les numéros de ligne et la distribution des échantillons par ligne, y compris la ligne chaude, et remplace le texte du code par des points de suspension. Le rapport reste utile - on sait toujours où le temps part - sans qu'une ligne de code quitte la machine.
- La **Provenance** (commit, patch, options de compilation, version de LLVM et `-mcpu`, pile MPI, bibliothèques chargées avec leur build-id) est un **tiroir dépliable depuis l'en-tête**, jamais une boîte de dialogue et jamais dans la vue principale.
- L'**assembleur** est un bloc dépliable dans le détail, avec le rappel qu'il est consultable ici mais n'est jamais envoyé au modèle.
- La **vue de comparaison** (`nunatak compare`, ticket 13) suit la même structure : une synthèse des écarts, puis un inventaire des Hotspots comparés par identité logique inlining compris, puis le détail d'un écart. Elle n'a pas été prototypée et reste à spécifier au moment de l'implémentation.

### Ce que le prototype a corrigé, et qui ne se voyait qu'à l'écran

- La première version du graphe **n'était pas un roofline** : les diagonales mémoire traversaient le plafond de calcul au lieu de s'y arrêter au point de rupture. Un roofline est l'enveloppe `min(pic de calcul, bande passante × intensité)`, et l'erreur n'apparaissait qu'au rendu.
- Un graphe en largeur fluide emporte sa typographie avec lui et devient disproportionné : il doit être **borné à sa taille naturelle**.
- Les étiquettes croisent nécessairement des lignes dans un plan log-log ; un **halo de la couleur du fond** les garde lisibles sans déplacer le trait.
- La Provenance en `alert()` bloque la page. Un tiroir est la bonne réponse, et pas seulement pour des raisons techniques.
