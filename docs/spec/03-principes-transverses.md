# 03 - Principes transverses

Ce chapitre est le plus important de la spec. Ce qui suit n'est pas une intention mais un **mécanisme** : chaque principe se traduit par un comportement observable, testable, et présent dans l'interface.

Un profileur qui se trompe sans le dire est pire qu'un profileur absent : il envoie son utilisateur optimiser la mauvaise boucle pendant trois semaines. Tout ce qui suit découle de ce constat.

## 1. Quatre registres, jamais confondus

C'est la distinction fondatrice. Quatre choses différentes peuvent mal tourner, elles ont quatre traitements distincts, et les mélanger est une faute de conception.

| Registre | Ce qui est en cause | Mécanisme | Exemple |
|---|---|---|---|
| **Qualité** | l'**incertitude** d'une valeur | `mesuré` / `estimé` / `indisponible`, avec rétrogradation motivée | compteurs multiplexés sous le seuil de couverture |
| **Niveau de résolution** | l'**identité** d'un Hotspot | `ligne` / `fonction` / `symbole` / `non résolu` | binaire strippé, adresse dans un trou entre symboles |
| **Dégradation fonctionnelle** | une **capacité** absente | annoncée avant le run, nommée, avec la marche à suivre | pas de frame pointers, donc pas de temps inclusif |
| **Invalidité** | une opération qui **n'a aucun sens** | refus, jamais rétrogradation | fusionner des Passes dont le binaire a changé |

**Pourquoi ces frontières comptent.** Quand l'attribution échoue, la Mesure reste exacte : ce temps a réellement été passé à cette adresse. Rétrograder sa Qualité serait une faute de sens et diluerait une étiquette construite pour parler d'incertitude numérique. Symétriquement, fusionner les FLOPs d'une passe avec le trafic mémoire d'une autre quand le code a changé entre les deux ne produit pas une intensité arithmétique imprécise : elle ne décrit rien. C'est une invalidité, et une invalidité se refuse.

## 2. La rétrogradation motivée

Une valeur nominalement mesurée retombe à `estimé` **accompagnée d'une raison lisible**. Les trois niveaux de Qualité ne bougent jamais ; seule la raison varie. Toute approximation nouvelle s'y rattache plutôt que d'inventer son vocabulaire.

Situations qui la déclenchent aujourd'hui :

- Calibration réalisée dans des conditions polluées ;
- compteurs multiplexés sous le seuil de couverture ;
- Hotspot sous le plancher statistique ;
- Passes incohérentes détectées par le groupe témoin ;
- distribution par ligne issue d'une table de lignes bruitée par l'optimisation ;
- bornes d'Analyse statique de boucle sur une microarchitecture au modèle d'ordonnancement approximatif.

**L'étiquette sans la raison ne sert à rien.** Partout où une valeur estimée s'affiche, sa raison est accessible.

## 3. On ne comble jamais un trou par une invention

Trois applications concrètes, chacune contraignante :

- **Règle d'étendue.** Une adresse n'est attribuée que si elle tombe dans `[st_value, st_value + st_size)` d'un symbole. Une adresse dans un trou entre symboles devient un Hotspot non résolu, affiché `libfoo.so+0x3a1c`, **jamais rattachée au symbole précédent**. La pratique répandue consiste à faire l'inverse ; c'est la seule façon qu'aurait ce système de mentir avec aplomb.
- **Pas d'extrapolation entre Loci.** Les Hotspots des rangs non échantillonnés sont `indisponible`, jamais déduits de leurs voisins.
- **`indisponible` n'est pas zéro.** Une grandeur absente s'écrit ainsi, jamais par une case vide sans explication ni par une valeur nulle.

## 4. Dégrader, pas refuser

**Tout prérequis externe absent produit une dégradation fonctionnelle nommée, annoncée avant le run, jamais un refus.** Cela vaut pour les piles d'appels, LLVM, le source, Node et pi, les collecteurs, `mpicc`.

Deux exceptions, et deux seulement :

- **`--strict`** transforme volontairement toute dégradation en erreur, pour les usages scriptés et la CI de performance ;
- l'**invalidité** du registre 4, qui n'est pas une dégradation.

## 5. Le moteur analyse, le modèle explique

Le Diagnostic est déterministe et reproductible. L'Explication est générée, non reproductible, persistée à part et **toujours étiquetée « conseil »**.

Conséquences opérationnelles :

- le modèle ne reçoit **jamais d'assembleur brut**, ni x86, ni PTX, ni SASS : le lui donner reviendrait à lui demander de diagnostiquer, et c'est la classe d'entrée où son erreur est la moins détectable par l'utilisateur ;
- il ne reçoit **jamais un Hotspot sous le plancher statistique** ;
- **pas de source, pas d'Explication** : privé de source, le pipeline ne produit que de la généralité, ce qui décrédibilise sa sortie.

## 6. Exec et parse, jamais link

Tout collecteur externe est **exécuté en sous-processus** et sa sortie parsée. Aucun n'est lié.

C'est d'abord une contrainte de licence - lier du GPL rendrait l'œuvre combinée GPL, ce qu'interdit le choix BSD-3/MIT - mais c'est devenu un principe d'architecture à part entière, appliqué aussi à nos propres binaires, au pilotage du modèle de langage, et qui rend possible toute la [stratégie de test](../development/testing.md).

## 7. Ce qui varie est enregistré

Le produit ne peut pas garantir que deux sites obtiennent des résultats identiques : la version de LLVM, la pile MPI, les options de compilation, les seuils configurés diffèrent. La réponse n'est pas de figer ces variables mais de les **inscrire dans la Provenance** du Run.

**Une variation enregistrée n'est plus une variation cachée.** En particulier, les seuils qui gouvernent la Qualité sont configurables, mais leur valeur effective est inscrite dans le Run et affichée dans le rapport : on peut régler un seuil, on ne peut pas le régler en douce.

## 8. Prévenir avant, pas après

L'utilisateur paie son temps de calcul. Tout ce qui manquera est annoncé **avant** de consommer l'allocation : un sous-ensemble léger du diagnostic s'exécute au début de chaque `run`, annonce les dégradations et la marche à suivre, puis continue.
