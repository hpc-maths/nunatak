# 11 - Interface en ligne de commande

Référence : [ADR 0007](../adr/0007-surface-cli.md).

## Ce que `doctor` vérifie

- l'inventaire des trois catégories d'outils externes (chapitre 12) avec leurs **versions** ;
- les permissions : niveau `paranoid` de perf, `ERR_NVGPUCTRPERM` ;
- le binaire cible : `-g`, frame pointers, `-lineinfo`, présence d'un `.dSYM` ou d'une carte de debug ;
- l'utilisabilité de `mpicc`, et il construit la sonde réseau ;
- la version de LLVM et la couverture `-mcpu` de la microarchitecture détectée.

**Deux règles de méthode**, tirées de faits constatés :

- **ne jamais se fier à `xcrun --find`** : sur une machine où `xcode-select` pointe vers un Xcode désinstallé, il déclare absents `dsymutil`, `nm` et `atos` qui sont pourtant dans `/usr/bin` ;
- **ne jamais se fier au seul `PATH`** : la formule Homebrew `llvm` est `keg_only`, donc jamais liée.

`doctor` **sonde les chemins et invoque les outils**. Constater une présence ne suffit pas.

Un **sous-ensemble bon marché s'exécute automatiquement au début de `run`** - pas de construction, pas de benchmark, quelques dizaines de millisecondes. Il annonce ce qui sera dégradé **puis continue**.

## Sortie terminal

C'est une sortie de première classe : sur un cluster, l'affichage de `run` atterrit dans un **fichier de log de job**, pas dans un terminal.

- **Elle détecte son support.** Sur un terminal : couleur et diffusion au fil de l'eau de la génération du modèle. Hors terminal : ni couleur, ni réécriture de ligne, ni barre de progression, mais des lignes horodatées lisibles dans un `tail -f` comme dans un fichier relu trois semaines plus tard.
- **Trois moments** : le `doctor` léger avant le lancement ; l'avancement aux étapes réelles pendant - Calibration, Passe, rapatriement par rang, analyse - **sans fausse précision sur le temps restant** ; le résumé à la fin, qui reprend le premier niveau du rapport puis les dégradations puis les chemins.
- **Même vocabulaire que le rapport.**
