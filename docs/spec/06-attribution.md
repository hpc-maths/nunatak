# 06 - Attribution

Référence : [ADR 0004](../development/decisions/0004-source-attribution.md), révisé sur deux points par l'[ADR 0005](../development/decisions/0005-packaging-and-distribution.md).

L'attribution est la fondation du produit, pas un détail de présentation : sans elle il n'y a pas de source à montrer, donc pas d'Explication, pas de comparaison entre Runs, et un roofline dont les points ne désignent rien.

## Piles d'appels

Elles servent à trois choses : rattacher les feuilles de bibliothèque au code utilisateur (sans quoi un `dgemm` chaud dans OpenBLAS est un Hotspot sans source), donner un temps inclusif, et reconstituer les piles mixtes Python. **Elles n'entrent pas dans l'identité du Hotspot.**

Ordre décidé à froid par `doctor` :

1. **`lbr`** si le processeur le propose : une trentaine de frames pour un coût quasi nul, sans contrainte de compilation. Intel en pratique.
2. **`fp`** si le binaire et ses bibliothèques ont des frame pointers, vérifié par sondage des prologues sur un échantillon de symboles - ce qui donne un **taux**, pas un oui/non.
3. **aucune pile**, et c'est une dégradation nommée.

`dwarf` reste disponible **sur demande explicite seulement**, avec annonce du coût et baisse automatique de la fréquence : recopier 8 Ko de pile par échantillon représente de l'ordre de 500 Mo/s à 1 kHz sur 64 threads, incompatible avec le budget de 10 %.

Coût assumé de l'absence de contexte dans l'identité : un `matvec` générique appelé par trois solveurs fusionne en un point de roofline moyen. Les piles étant persistées, un éclatement par contexte reste ajoutable sans toucher au pivot.

## Python

- L'interpréteur n'expose ses frames que si `PYTHONPERFSUPPORT=1` est dans l'environnement du lancement.
- **Les frames de l'interpréteur ne sont jamais des Hotspots** : elles sont repliées sur la frame Python la plus interne au-dessus d'elles, ce qui attribue le temps d'interprétation à la fonction Python interprétée - son sens exact.
- Les feuilles natives des **extensions** (numpy, pybind11, Cython) restent des Hotspots natifs traités par le chemin DWARF ordinaire, avec la frame Python appelante visible dans la pile.
- Sur CPython antérieur à 3.12 et sur macOS, py-spy échantillonne temporellement : les Hotspots Python existent avec un niveau de résolution complet mais leurs Compteurs bruts sont `indisponible`. **Les deux flux ne sont jamais fusionnés dans une même pile** : deux horloges, deux déclencheurs, ce serait du double comptage habillé en mesure.
- Tout ce qui écrit une perf map (Numba, un JIT) entre par la même porte sans code spécifique.

## macOS

Le chemin macOS sert la **boucle de développement courte**, pas le verdict de référence. On ne cherche pas à rivaliser avec Instruments, qui restera meilleur pour l'exploration interactive, la timeline système, l'E/S et le thermique.

- `LC_UUID` remplace le build-id, au même rôle exact.
- **L'exécutable ne contient aucune section DWARF.** L'information vit dans un `.dSYM` ou dans la **carte de debug** pointant vers les `.o`. Conséquence sans équivalent Linux : **un `make clean` détruit rétroactivement toute attribution au niveau ligne**, et un binaire copié seul depuis une autre machine n'en a jamais eu.
- Les piles sont **gratuites et fiables** : l'ABI arm64 d'Apple impose le maintien du pointeur de trame et les deux échantillonneurs renvoient des backtraces complètes. L'échelle `lbr > fp > rien` y est sans objet.
- Avec **`xctrace`**, les échantillons portent des adresses et l'UUID du module : on symbolise soi-même et toute l'échelle de résolution s'applique. Avec **`/usr/bin/sample`**, la sortie est déjà symbolisée et agrégée, on ne voit jamais d'adresse : résolution plafonnée à `fonction`, pas d'inlining, et **la règle d'étendue est inapplicable**. On hérite alors de l'attribution d'Apple, et on le déclare via le niveau de résolution.

## GPU

- `-lineinfo` (nvcc) ou `-g` (hipcc) donne la correspondance instruction vers ligne : on obtient l'attribution par ligne **à l'intérieur** du kernel, y compris à travers les fonctions `__device__` inlinées, ce qui est le cas général. Sans, résolution `symbole` et aucun extrait envoyé au modèle.
- `-lineinfo` **n'est pas exigé** mais `doctor` le réclame avant le run.
- Sur AMD, la corrélation instruction vers source passe par l'ATT, nettement moins établie. En v1 : nom de kernel et compteurs agrégés, attribution par ligne **`indisponible`**. Asymétrie NVIDIA/AMD **déclarée, pas promise**.
- **Groupement par nom** de kernel. La configuration de lancement (grille, bloc, stream, taille) est un détail interne porté par les Événements.
- Le **site d'appel côté hôte** est collecté mais **borné à un échantillon de lancements par nom de kernel**.

## Source

- **Recherche** : le chemin DWARF tel quel, puis une correspondance fournie par l'utilisateur (`--source-map`), puis une recherche par nom de base sous la racine du dépôt. **En cas de correspondances multiples ambiguës, on ne choisit pas** : le Hotspot reste sans source, avec la raison.
- **Vérification de péremption** : l'empreinte MD5 de la table de lignes DWARF 5, émise par défaut par clang. Empreinte présente et discordante, le source n'est **ni affiché ni envoyé**, et le rapport dit pourquoi. Sans cette règle, un développeur ayant édité son code depuis le run verrait un rapport pointant des lignes qui ont bougé.
- **Seuls les extraits nécessaires sont embarqués** dans le Run : corps de la fonction physique, frames inline chaudes, quelques lignes de contexte. Jamais les fichiers entiers.
- **Deux commutateurs distincts**, parce que ce sont deux risques différents : `--no-source` retire le texte du **rapport** ; un **accord explicite et mémorisé par projet** est demandé au premier usage d'un provider **distant**. Aucun accord si le provider configuré dans Pi est local.

## Stabilité inter-passes

- L'**ASLR et le réordonnancement tombent par construction** grâce à la normalisation en offsets (invariant I3).
- Une **recompilation entre Passes est une invalidité, pas une incertitude** : refus de fusion **au niveau du module**, pas rétrogradation. Les Hotspots des modules dont l'identité physique a changé sont présentés par Passe, sans fusion ni placement sur le roofline. Recompiler une bibliothèque n'invalide pas les mesures de `libmpi`.
- **Comparer deux versions, c'est deux Runs**, jamais deux Passes.

## Rapports d'optimisation du compilateur

Acceptés **s'ils sont déjà présents** à côté du binaire ou des objets, jamais provoqués par une recompilation. Rattachés par `(fichier, ligne)`, et **non utilisés si leur correspondance avec le binaire exécuté n'est pas vérifiable** : un rapport périmé déclarant une boucle non vectorisée alors que le binaire courant la vectorise serait pire que rien.
