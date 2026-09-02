# 06 - Attribution

Référence : [ADR 0004](../development/decisions/0004-source-attribution.md), révisé sur deux points par l'[ADR 0005](../development/decisions/0005-packaging-and-distribution.md).

Ce qui est construit et documenté a rejoint le site : la règle
d'étendue, les niveaux de résolution et le repli sur `addr2line` ou
`atos` sont dans [Attribution](../guide/attribution/index.md) et
[resolution levels](../reference/resolution-levels.md) ; l'échelle des
piles d'appels et leur absence dans l'identité d'un Hotspot dans
[Call stacks](../guide/stacks/index.md) ; les deux chemins Python dans
[Python applications](../guide/python/index.md) ; le `.dSYM`, la carte
de debug et les deux échantillonneurs dans
[macOS](../guide/macos/index.md) ; les deux commutateurs du source dans
[Source](../guide/source/index.md) et
[Explanations](../guide/explanations/index.md) ; la stabilité
inter-passes et le refus de fusion après recompilation dans
[Multi-pass runs](../guide/multi-pass/index.md).

## Reste à construire

- **Attribution GPU** : `-lineinfo` (nvcc) ou `-g` (hipcc) donne
  l'attribution par ligne **à l'intérieur** du kernel, inlining
  `__device__` compris ; sans, résolution `symbole` et aucun extrait
  envoyé au modèle. `doctor` le réclame avant le run sans l'exiger.
  Groupement par nom de kernel, la configuration de lancement restant
  un détail porté par les Événements. Site d'appel côté hôte collecté,
  borné à un échantillon de lancements par nom.
- **Asymétrie NVIDIA/AMD, déclarée et non promise** : sur AMD la
  corrélation instruction vers source passe par l'ATT, nettement moins
  établie, donc nom de kernel et compteurs agrégés, attribution par
  ligne `indisponible`.
- **Rapports d'optimisation du compilateur** : acceptés s'ils sont
  déjà présents à côté du binaire, jamais provoqués par une
  recompilation, rattachés par `(fichier, ligne)`, et ignorés si leur
  correspondance avec le binaire exécuté n'est pas vérifiable - un
  rapport périmé déclarant une boucle non vectorisée alors que le
  binaire courant la vectorise serait pire que rien.
