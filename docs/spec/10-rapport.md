# 10 - Rapport

Référence : [ADR 0006](../development/decisions/0006-html-report-design.md). Prototype de référence sur la branche `prototype/rapport-html` (commit `6c5ec2f`).

## Modes et tiroirs
- L'**assembleur** est un bloc dépliable dans le détail, avec le rappel qu'il n'est jamais envoyé au modèle.

## Pièges vérifiés au rendu

Trois défauts constatés sur le prototype, invisibles à la lecture du code :

1. la première version du graphe **n'était pas un roofline** : les diagonales mémoire traversaient le plafond de calcul au lieu de s'arrêter au point de rupture. À couvrir par un test unitaire sur l'enveloppe ;
2. un graphe en largeur fluide **emporte sa typographie** et devient disproportionné : il doit être borné à sa taille naturelle ;
3. les étiquettes croisent nécessairement des lignes en plan log-log : un **halo de la couleur du fond** les garde lisibles sans déplacer le trait.
