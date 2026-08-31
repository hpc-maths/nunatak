# 13 - Tests et intégration continue

Référence : [ADR 0008](../adr/0008-strategie-test-ci.md).

## Le pivot de la stratégie

Le principe « exec + parse » a une conséquence exploitable : **tout ce que nunatak consomme des collecteurs est du texte ou des fichiers** - un `perf.data`, un export sqlite de `nsys`, un CSV de `ncu`, un rapport mpiP, un `.trace` d'`xctrace`, une carte de debug Mach-O.

> **On enregistre une fois sur du vrai matériel, on rejoue indéfiniment sans matériel.**

Cela impose une contrainte d'architecture ([architecture](../development/architecture.md)) : **les adaptateurs doivent être substituables par une source d'enregistrements**.

**Le corpus se capture, il ne s'écrit pas.** Un corpus rédigé à la main ne teste que l'idée qu'on se fait des sorties d'outils, jamais leurs sorties réelles - c'est précisément l'erreur qui laisserait une CI verte sur un parseur cassé. Il est produit par un mode d'enregistrement de nunatak lui-même.

## Deux corpus, deux actifs durables

| Corpus | Contenu | Sert à |
|---|---|---|
| **Binaires figés** | avec DWARF, sans, strippés, fortement inlinés, vectorisés AVX-512 et SVE, sans frame pointers, sans `-lineinfo` | attribution, symbolisation, analyse statique |
| **Enregistrements** | sorties réelles de chaque collecteur sur chaque plateforme | parseurs, ingestion, tout l'aval |

Ce sont les deux actifs les plus durables du projet. Ils servent à la fois la non-régression et la veille de version.

## La frontière

**Testable sans matériel spécial, donc bloquant pour une fusion.** C'est l'écrasante majorité du code, et notamment **la totalité de ce qui peut mentir à l'utilisateur** :

- tous les **parseurs**, versionnés par version d'outil ;
- toute la **chaîne d'attribution** : symbolisation, règle d'étendue, chaînes d'inlining, repli des frames d'interpréteur, normalisation en offsets ;
- tout le **moteur d'analyse déterministe** : enveloppe roofline `min(pic, bande passante × intensité)`, classification, propagation de la Qualité le long du Linéage, plancher statistique, agrégat « autres », refus de fusion inter-passes ;
- la **génération du rapport** et la mini-app TypeScript, alimentées par un pivot figé ;
- la **CLI** : codes de sortie, propagation de celui de l'application, `--strict` et son code 121, sorties JSON, cascade de configuration, détection du support de sortie.

**Exige du matériel réel, donc ne peut pas bloquer une fusion** : la Calibration, l'overhead réel face au budget de 10 %, le fait que les commandes de collecte tournent vraiment avec leurs permissions, le passage à l'échelle MPI multi-nœuds.

## Trois étages

**Étage 1 - runners hébergés, bloquant.** GitHub fournit `ubuntu-24.04-arm` et `ubuntu-26.04-arm` (arm64) ainsi que `macos-14` et `macos-15` (Apple Silicon), gratuits et illimités sur les dépôts publics. Cet étage couvre le rejeu des deux corpus, **toute la matrice de build des wheels**, et **tout le chemin macOS de bout en bout** - le shim `/usr/bin/xctrace` sans Xcode, le repli sur `/usr/bin/sample`, `dsymutil`, la carte de debug pointant vers les `.o`, `atos`.

**Réserve à inscrire dans la spec** : ce sont des machines virtuelles, où **les PMU sont en général non exposées**. On y vérifie que les commandes se lancent, que les permissions sont correctement diagnostiquées et que les sorties se parsent, **pas** que les compteurs remontent des valeurs justes.

**Étage 2 - runner auto-hébergé**, station Linux avec de vraies PMU et éventuellement un GPU. Seul étage qui vérifie qu'un compteur remonte vraiment. Non bloquant, la nuit.

**Étage 3 - campagnes périodiques sur cluster**, un centre GENCI pour NVIDIA et l'échelle MPI, LUMI ou équivalent pour AMD. Quelques fois par an.

> **La livraison d'une campagne matérielle n'est pas une coche verte, c'est le rafraîchissement du corpus d'enregistrements.** C'est ce qui transforme un accès matériel rare en actif durable : une campagne rend significatifs les six mois de CI qui suivent.

## Les trois cas durs

**La Calibration : des propriétés, jamais des chiffres.** Un Plafond ne dépasse jamais le pic théorique de la table ; c'est un **maximum** de répétitions et non une moyenne ; deux Calibrations successives restent dans une tolérance ; le repli théorique s'active ; la rétrogradation se déclenche en conditions polluées.

**Le pipeline LLM : le prompt est une fonction pure du pivot**, donc un artefact sous test par capture d'instantané. Tout changement de ce que le modèle voit devient un diff relu en revue. C'est ce qui garde la classe de bug la plus dangereuse - source envoyé sous `--no-source`, Hotspot sous le plancher, assembleur qui fuit - qui ne serait garantie par rien d'autre d'exécutable. S'y ajoutent la détection des erreurs de provider et l'étiquetage en « conseil ». **La qualité du conseil ne barre aucune fusion.**

**Le rapport** : instantanés sur le HTML produit depuis un pivot figé, plus quelques parcours de navigateur sur les parties interactives - substitution des vues, mode `--no-source`, cas « hors du roofline ». Et un **test unitaire sur la géométrie du roofline**, motivé par un bug réellement introduit au prototype et invisible à la lecture du code.

## Ce qu'on assume de ne pas pouvoir tester

Écrit noir sur blanc plutôt que passé sous silence :

- la justesse absolue des compteurs sur les microarchitectures qu'on ne possède pas ;
- l'overhead réel à l'échelle ;
- MPI au-delà de ce que les campagnes atteignent ;
- la qualité des conseils ;
- les ISA et cibles `gfx` hors wheel.

**Ce ne sont pas des trous, ce sont les zones que le produit couvre par son honnêteté plutôt que par ses tests.** `doctor` annonce ce qu'il ne sait pas faire, la Provenance enregistre dans quelles conditions un chiffre a été produit, la rétrogradation motivée dit pourquoi une valeur est incertaine. **Un outil qui ne peut pas tout tester doit déclarer ce qu'il ne sait pas** - c'est le principe 7 du chapitre 03, et la stratégie de test en est le dernier maillon.
