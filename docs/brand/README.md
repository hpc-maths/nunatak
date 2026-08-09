# Identité visuelle de nunatak

Un nunatak est un sommet rocheux qui émerge au-dessus de la calotte glaciaire : ce qui dépasse du bruit.

## Le principe du dessin

La silhouette **n'illustre pas une montagne, elle trace le roofline**.

- Le **flanc gauche** monte en diagonale : le régime où la performance est plafonnée par la bande passante mémoire.
- Le **sommet plat** est le plafond de calcul. Seul le pic principal l'atteint ; le second sommet reste dessous, comme la plupart des kernels.
- Le **point chaud** marque le *ridge point*, la rupture entre les deux régimes. C'est le seul élément coloré de la marque, parce que c'est le seul endroit où il faut regarder.
- La **glace** coupe le massif et laisse deviner sa masse immergée : ce que l'outil ne mesure pas, il le déclare au lieu de le taire.

## Fichiers

| Fichier | Usage |
|---|---|
| `nunatak-mark.svg` | Marque couleur sur fond clair |
| `nunatak-mark-dark.svg` | Marque couleur sur fond sombre |
| `nunatak-mark-mono.svg` | Monochrome, hérite de `currentColor` (gravure, tampon, une seule encre) |
| `nunatak-mark-small.svg` | 24 px et moins : sans masse immergée, point de rupture grossi |
| `nunatak-lockup.svg` | Marque et mot-symbole, disposition horizontale |

En dessous de 24 px, le filigrane de la masse immergée devient une salissure et l'accent chaud reste la seule signature reconnaissable : utiliser la variante réduite, jamais la marque complète mise à l'échelle.

## Palette

| Rôle | Hex |
|---|---|
| Roche | `#14324A` |
| Glace | `#BFE6F7` |
| Eau de fonte (glace sur fond sombre) | `#2E7FA8` |
| Point chaud | `#E2701F` (`#FF9A5A` sur fond sombre) |
| Névé (roche sur fond sombre) | `#E8F1F7` |

Le chaud est rationné : il ne sert qu'au point de rupture et aux alertes. Partout ailleurs, la marque reste glaciaire.

## Typographie

Le mot-symbole est en **chasse fixe**, parce que c'est sous cette forme que l'utilisateur rencontrera le nom le plus souvent : au début d'une ligne de commande.

## À faire avant diffusion

Le mot-symbole de `nunatak-lockup.svg` est encore du texte vivant, donc tributaire des polices présentes sur la machine qui affiche le fichier. Il doit être **converti en courbes** avant toute publication du logo.
