# 10 - Rapport

Référence : [ADR 0006](../adr/0006-design-rapport-html.md). Prototype de référence sur la branche `prototype/rapport-html` (commit `6c5ec2f`).

## Contrainte

Mini-app TypeScript compilée, embarquée comme asset statique. **Auto-contenue, aucune requête externe**, utilisable sur un cluster sans serveur et lisible dans dix ans depuis un fichier archivé.

## Trois niveaux de lecture

| Niveau | Contenu | Rôle |
|---|---|---|
| 1 | **Synthèse rédigée** : constats classés par part du temps, chacun avec ses preuves chiffrées, puis « ce que ce rapport ne dit pas » | par où commencer |
| 2 | **Inventaire dense** : tous les Hotspots, triable et filtrable, Qualité et Niveau de résolution en colonnes propres | trouver un Hotspot précis |
| 3 | **Détail d'un Hotspot** : et **c'est là que vit le roofline** | comprendre un cas |

**Les trois niveaux se substituent, ils ne cohabitent jamais.** Inventaire et détail occupent la même zone ; on ne défile que dans un seul contenu à la fois. Le retour se fait par un bouton explicite et par `Échap`.

Le **détail se répartit sur deux colonnes** dès qu'il en a la place : à gauche le roofline, les métriques, les faits déterministes et l'Explication ; à droite le source annoté, la ventilation par frame inline et l'assembleur dépliable.

## Le roofline au troisième niveau

Ce déplacement n'est pas cosmétique. Un roofline global devrait mélanger CPU et GPU, dont les Plafonds n'ont rien à voir, ou imposer un sélecteur d'appareil. **Contextualisé sur un Hotspot, l'appareil devient implicite et le graphe est correct par construction.**

Il montre les Plafonds, le Hotspot sélectionné en évidence, et les autres Hotspots **du même appareil** en points pâles pour l'échelle.

**Un Hotspot qui ne peut pas être placé le dit à l'endroit où on l'attend** : quand l'utilisateur ouvre un Hotspot non résolu ou l'agrégat « autres », le graphe est **remplacé par un encadré qui explique pourquoi**, au lieu de disparaître en silence ou d'afficher un graphe vide.

## Vocabulaire visuel de l'incertitude

**Deux registres, deux canaux, jamais confondus.**

| Registre | Canal | Codage |
|---|---|---|
| **Qualité** | couleur et forme | `mesuré` plein, `estimé` hachuré, `indisponible` pointillé |
| **Niveau de résolution** | étiquette texte neutre | `ligne`, `fonction`, `symbole`, `non résolu`, sans couleur |

Le codage de la Qualité est **le même partout** : pastille dans une table, barre de part du temps, point du roofline. Un Hotspot estimé y est un cercle pointillé, un Hotspot mesuré un disque plein.

**La rétrogradation motivée affiche sa raison**, pas seulement son étiquette : « rétrogradé en estimé : compteurs multiplexés, couverture 63 % sous le seuil de 80 % ».

## Rendre l'incomplétude lisible

- **« Ce que ce rapport ne dit pas »** clôt la synthèse et rassemble ce qui manque : temps non attribuable, agrégat « autres » et son plancher, Plafonds estimés, kernels sans `-lineinfo`, rangs non échantillonnés. Rassembler ces aveux en un endroit nommé les rend lisibles ; les disperser en notes de bas de page les rendrait invisibles.
- **Une grandeur absente s'écrit `indisponible`**, jamais zéro ni case vide sans explication.
- La **couverture d'échantillonnage** est énoncée en tête de synthèse, pas en annexe.
- L'**Explication** est toujours dans un cadre distinct étiqueté « conseil, généré par un modèle, non reproductible ». Absente, le rapport dit pourquoi.

## Modes et tiroirs

- **`--no-source`** conserve les numéros de ligne et la distribution des échantillons, y compris la ligne chaude, et remplace le texte du code par des points de suspension. On sait toujours où le temps part, sans qu'une ligne de code quitte la machine.
- La **Provenance** est un **tiroir dépliable depuis l'en-tête** : jamais une boîte de dialogue, jamais dans la vue principale.
- L'**assembleur** est un bloc dépliable dans le détail, avec le rappel qu'il n'est jamais envoyé au modèle.

## Vue de comparaison

`nunatak compare` suit la même structure à trois niveaux : synthèse des écarts, inventaire des Hotspots comparés par **identité logique inlining compris**, détail d'un écart.

- l'**incertitude statistique est portée dans l'écart affiché** : un gain de 3 % entre deux Hotspots à 8 % d'erreur relative n'est pas un gain, et le rapport le dit ;
- ce qui n'est pas comparable - Machine, nombre de rangs ou données d'entrée différents - est **affiché en étant déclaré non comparable**, jamais maquillé.

Cette vue n'a pas été prototypée et reste à détailler à l'implémentation.

## Cohérence avec le terminal

Le résumé terminal reprend **le premier niveau** du rapport et emploie le même vocabulaire. Qui ne lit que le log apprend moins de détails, **jamais moins sur la solidité de ses chiffres**.

## Pièges vérifiés au rendu

Trois défauts constatés sur le prototype, invisibles à la lecture du code :

1. la première version du graphe **n'était pas un roofline** : les diagonales mémoire traversaient le plafond de calcul au lieu de s'arrêter au point de rupture. À couvrir par un test unitaire sur l'enveloppe ;
2. un graphe en largeur fluide **emporte sa typographie** et devient disproportionné : il doit être borné à sa taille naturelle ;
3. les étiquettes croisent nécessairement des lignes en plan log-log : un **halo de la couleur du fond** les garde lisibles sans déplacer le trait.
