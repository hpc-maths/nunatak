# 09 - Explication

Référence : tickets 08, 09 et 12.

## Contrat

Le modèle **explique et suggère à partir de faits déjà établis**. Il ne diagnostique pas, ne mesure pas, ne classe pas.

L'Explication est :

- **non reproductible**, et assumée comme telle ;
- **persistée séparément** du pivot mesuré ;
- **toujours étiquetée « conseil »**, jamais mélangée aux faits déterministes ;
- **régénérable sans reprofiler**.

## Ce que le modèle reçoit

| Reçoit | Ne reçoit jamais |
|---|---|
| le Diagnostic du Hotspot | de l'assembleur brut : x86, PTX, SASS |
| les faits déterministes du chapitre 08 | un Hotspot sous le plancher statistique |
| le source de la fonction physique | du source non vérifié ou périmé |
| les extraits des frames inline chaudes | du source quand `--no-source` est actif |
| la distribution des échantillons par ligne | un fait `indisponible` |

**Pourquoi jamais d'assembleur** : le lui donner reviendrait à lui demander de diagnostiquer, ce que le principe 5 du chapitre 03 interdit. C'est aussi la classe d'entrée où son erreur est la moins détectable par l'utilisateur - personne ne relit 400 lignes de SASS pour vérifier une affirmation.

**Sans source, pas d'Explication.** Le pipeline est « faits déterministes + source vers conseil » ; privé de source il ne produit que de la généralité, ce qui décrédibilise sa sortie. Le rapport affiche alors le Diagnostic, entier, et **la raison de l'absence** : pas de source disponible pour ce module, kernel compilé sans `-lineinfo`, Hotspot non résolu, sous le plancher statistique.

## Couche d'accès

**Pi** (le toolkit, pi.dev) piloté **en sous-processus RPC**, ce qui étend « exec + parse » au modèle de langage.

**La configuration de Pi est la source unique des providers et des modèles.** nunatak ne la duplique pas, ne la surcharge pas, et n'expose aucun réglage de modèle dans sa propre configuration.

La spec **recommande une classe de modèle** - orienté code, avec capacité de raisonnement - et non un modèle figé.

**Node.js et pi sont des dépendances déclarées** sur conda-forge et spack, donc présentes par défaut sur le chemin nominal. Leur absence produit « Explication indisponible : Node.js ou pi introuvable », annoncée par `doctor`, et le run se déroule.

## Exécution

- **Appels parallèles** : la latence observée est de 24 à 60 secondes par kernel, ce qui rend le séquentiel inutilisable dès une poignée de Hotspots.
- **Diffusion au fil de l'eau** dans le terminal quand la sortie est un terminal.
- **Détection obligatoire des erreurs de provider** : une erreur d'authentification, de quota ou de réseau doit être distinguée d'une réponse vide et remontée telle quelle. Un pipeline qui avale silencieusement une erreur produit un rapport sans conseils sans que personne ne sache pourquoi.

## Séparation d'avec la mesure

**L'Explication est séparée de la mesure par nécessité, pas par confort.** `run` s'exécute dans un job, sur des nœuds de calcul qui n'ont généralement **aucune sortie réseau** : mesure et explication ne diffèrent pas seulement par leur durée, elles s'exécutent à des endroits différents.

`run` **tente** l'Explication et n'en dépend jamais. À défaut, il dégrade de façon nommée en donnant la commande exacte à rejouer depuis un nœud de connexion.

## Confidentialité

Du code source quitte la machine. Deux mécanismes distincts, décrits au chapitre 06 :

- **accord explicite et mémorisé par projet** au premier usage d'un provider **distant**, formulé sans détour ;
- **aucun accord demandé** si le provider configuré dans Pi est local, ce qui donne la voie de sortie propre à un site qui ne peut rien laisser partir.

## Test

Le pipeline est non reproductible, mais **le prompt est une fonction pure du pivot**. Il est donc un artefact sous test, capturé par instantané : tout changement de ce que le modèle voit devient un diff relu en revue.

C'est ce qui garde la classe de bug la plus dangereuse - envoyer du source sous `--no-source`, envoyer un Hotspot sous le plancher, laisser filer de l'assembleur - qui ne serait garantie par rien d'autre d'exécutable.

**La qualité du conseil ne barre aucune fusion** : elle est relue par un humain sur un jeu de cas figés à chaque version.
