# Décision : stratégie de test et CI sur matériel hétérogène

Type: grilling
Blocked by: 05, 07, 10, 13, 15
Status: resolved

## Question

Comment teste-t-on un outil dont la valeur dépend d'un matériel que la CI n'a pas ?

Le produit doit fonctionner sur des CPU x86 et ARM variés, des GPU des deux fournisseurs, un cluster MPI multi-nœuds et un Mac. Aucun service d'intégration continue courant ne fournit tout cela, et une partie des mesures n'a de sens que sur du vrai matériel.

Ce que les tickets résolus ont déjà fourni ou exigé :

- **Le corpus de binaires figés** du ticket 13, avec leurs sorties attendues : avec DWARF, sans, strippés, fortement inlinés, vectorisés AVX-512 et SVE. C'est la pièce maîtresse et elle sert aussi à la veille de version.
- **Un job de CI sur chaque rc et majeure LLVM** qui diffe les `-mcpu` et rejoue le corpus (ticket 13), étendu à tous les outils orchestrés.
- **La validation par microarchitecture** du symboliseur et de l'analyse statique de boucle (ticket 07).
- **L'attribution sur des binaires volontairement dégradés** : sans `-g`, strippés, sans frame pointers, sans `-lineinfo` (ticket 07).
- **La matrice de build des wheels** : manylinux x86-64 et aarch64, macOS arm64, plus les trois cibles `gfx` (ticket 13).

À trancher : ce qui est testable **sans matériel** en rejouant des sorties de collecteurs enregistrées, puisque toute l'architecture est « exec + parse » et que ce principe rend l'enregistrement possible ; ce qui exige du matériel réel et comment on y accède (runners auto-hébergés, allocation sur un centre partenaire, rien) ; ce qui bloque une fusion contre ce qui tourne la nuit ou à la demande ; comment on teste une Calibration dont la valeur dépend de la machine ; comment on teste un pipeline LLM non reproductible (tickets 08, 09) ; comment on teste le rapport, qui est une mini-app TypeScript ; et **ce qu'on assume de ne pas pouvoir tester**, écrit noir sur blanc plutôt que passé sous silence.

## Answer

Décision prise en session /grilling ; arbitrage complet dans `docs/adr/0008-strategie-test-ci.md`.

**Le principe « exec + parse » du ticket 04 a une conséquence inexploitée** : tout ce que nunatak consomme des collecteurs est du texte ou des fichiers. On peut donc **enregistrer une fois sur du vrai matériel, puis rejouer indéfiniment sans matériel**. C'est le pivot de la stratégie, et le **corpus d'enregistrements se capture, il ne s'écrit pas** - un corpus rédigé à la main ne validerait que notre lecture des formats, jamais les formats réels.

**Frontière.** Sans matériel spécial, donc bloquant pour une fusion : tous les parseurs, toute la chaîne d'attribution du ticket 07, tout le moteur d'analyse déterministe, la génération du rapport, et la CLI du ticket 15. C'est l'écrasante majorité du code et **la totalité de ce qui peut mentir à l'utilisateur**. Exige du matériel réel, donc non bloquant : la Calibration, l'overhead réel, le fait que les commandes de collecte tournent vraiment, et le passage à l'échelle MPI.

**Trois étages.** (1) Runners hébergés, bloquants : GitHub fournit arm64 Linux et macOS Apple Silicon, gratuits et illimités sur dépôt public. Cet étage couvre toute la matrice de wheels du ticket 13 et **tout le chemin macOS du ticket 07 de bout en bout**. Réserve : ce sont des VM, les PMU n'y sont en général pas exposées. (2) Un runner auto-hébergé avec de vraies PMU, la nuit. (3) Des campagnes périodiques sur cluster, dont **la livraison est le rafraîchissement du corpus** plutôt qu'une coche verte - c'est ce qui transforme un accès matériel rare en actif durable.

**Trois cas durs.** La Calibration se teste par **invariants, jamais par chiffres** (un Plafond ne dépasse pas le pic théorique, c'est un maximum et non une moyenne, le repli s'active, la rétrogradation se déclenche). Le pipeline LLM se teste par le **prompt, fonction pure du pivot**, capturé en instantané : tout changement de ce que le modèle voit devient un diff relu, ce qui garde la classe de bug la plus dangereuse - source envoyé sous `--no-source`, Hotspot sous le plancher, assembleur qui fuit. Le rapport se teste par instantanés HTML plus quelques parcours de navigateur, avec un test unitaire sur la géométrie du roofline, `min(pic, bande passante × intensité)`, qui est exactement le bug introduit au ticket 14.

**Ce qu'on assume de ne pas tester** est écrit noir sur blanc : justesse absolue des compteurs sur le matériel qu'on ne possède pas, overhead à l'échelle, MPI au-delà des campagnes, qualité des conseils, ISA et cibles `gfx` hors wheel. Ce ne sont pas des trous mais **les zones que le produit couvre par son honnêteté plutôt que par ses tests** : `doctor`, la Provenance et la rétrogradation motivée. Un outil qui ne peut pas tout tester doit déclarer ce qu'il ne sait pas.
