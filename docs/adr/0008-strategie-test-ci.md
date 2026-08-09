# Stratégie de test : enregistrer une fois sur le matériel, rejouer partout

## Contexte et décision

Le produit doit fonctionner sur des CPU x86 et ARM variés, des GPU des deux fournisseurs, un cluster MPI multi-nœuds et un Mac. Aucun service d'intégration continue ne fournit tout cela, et une partie des mesures n'a de sens que sur du vrai matériel. La question n'était donc pas « comment tout tester » mais **où passe la frontière, et que fait-on de chaque côté**.

**Le principe fondateur du ticket 04, « exec + parse, jamais link », a une conséquence que personne n'avait exploitée** : tout ce que nunatak consomme des collecteurs est du texte ou des fichiers - un `perf.data`, un export sqlite de `nsys`, un CSV de `ncu`, un rapport mpiP, un `.trace` d'`xctrace`, une carte de debug Mach-O. On peut donc **enregistrer une fois sur du vrai matériel, puis rejouer indéfiniment sans matériel**. C'est le pivot de toute la stratégie.

**Le corpus d'enregistrements se capture, il ne s'écrit pas.** Un corpus rédigé à la main ne teste que l'idée qu'on se fait des sorties d'outils, jamais leurs sorties réelles : c'est précisément l'erreur qui laisserait une CI verte sur un parseur cassé. Il est donc produit par un mode d'enregistrement de nunatak lui-même, pendant les campagnes sur matériel réel.

**Et la livraison d'une campagne matérielle n'est pas une coche verte, c'est le corpus.** C'est ce qui transforme un accès matériel rare en actif durable : une campagne rend significatifs les six mois de CI qui suivent.

## Options considérées

- **Écrire le corpus à la main** à partir de la documentation des outils : écarté, il validerait notre lecture des formats et non les formats réels.
- **Ne faire aucune CI matérielle** et s'en remettre aux remontées de la communauté : écarté, rien ne vérifierait jamais que les commandes de collecte tournent réellement.
- **Louer des runners GPU en nuage pour chaque fusion** : écarté pour son coût, sans rapport avec la valeur ajoutée par rapport au rejeu du corpus.
- **Faire des campagnes matérielles un simple test de non-régression** : écarté au profit d'une campagne dont la sortie est le corpus, seule façon de rentabiliser un accès rare.
- **Affirmer des valeurs absolues de Calibration en CI** : écarté, la valeur *est* la machine. On affirme des invariants.
- **Juger la qualité des conseils du LLM par un modèle juge** : écarté, cela ajouterait du non déterministe pour valider du non déterministe, dans un projet qui a fait de la reproductibilité du Diagnostic sa ligne de fond.
- **Faire barrer une fusion par la qualité d'un conseil** : écarté, elle est relue par un humain sur un jeu de cas figés à chaque version.

## Conséquences

### La frontière

**Testable sans aucun matériel spécial, donc bloquant pour une fusion.** C'est l'écrasante majorité du code, et notamment **la totalité de ce qui peut mentir à l'utilisateur** :

- tous les **parseurs** de sorties de collecteurs, contre des enregistrements figés, versionnés par version d'outil détectée (ticket 04) ;
- toute la **chaîne d'attribution** du ticket 07 : symbolisation, règle d'étendue, chaînes d'inlining, repli des frames d'interpréteur Python, normalisation en offsets de module. C'est du DWARF et des ELF ou Mach-O figés, pas du matériel ;
- tout le **moteur d'analyse déterministe** : placement roofline, classification, propagation de la Qualité le long du Linéage, plancher statistique, agrégat « autres », refus de fusion inter-passes ;
- la **génération du rapport** et sa mini-app TypeScript, alimentées par un pivot figé ;
- la **CLI** du ticket 15 : codes de sortie, propagation de celui de l'application, `--strict` et son code 121, sorties JSON, cascade de configuration, détection du support de sortie.

**Exige du matériel réel, donc ne peut pas bloquer une fusion** : la Calibration, dont la valeur est la machine ; l'overhead réel face au budget de 10 % de l'ADR 0003 ; le fait que les commandes de collecte tournent vraiment sur chaque plateforme, permissions comprises ; le passage à l'échelle MPI multi-nœuds.

### Trois étages d'exécution

**Étage 1 - runners hébergés, bloquant.** GitHub fournit `ubuntu-24.04-arm` et `ubuntu-26.04-arm` (arm64) ainsi que `macos-14` et `macos-15` (Apple Silicon), et l'usage des runners standard est gratuit et illimité sur les dépôts publics : le projet étant BSD-3/MIT, tout cela lui est ouvert. Cet étage couvre bien plus que le rejeu du corpus : **la matrice de build des wheels du ticket 13 dans son intégralité**, et **tout le chemin macOS du ticket 07 de bout en bout** - le shim `/usr/bin/xctrace` sans Xcode, le repli sur `/usr/bin/sample`, `dsymutil`, la carte de debug pointant vers les `.o`, `atos`.

Réserve à inscrire dans la spec : ces runners sont des machines virtuelles, où **les PMU sont en général non exposées**. On y vérifie que les commandes se lancent, que les permissions sont correctement diagnostiquées et que les sorties se parsent, mais **pas** que les compteurs matériels remontent des valeurs justes. Ce n'est pas une lacune de la CI, c'est la frontière ci-dessus qui réapparaît.

**Étage 2 - un runner auto-hébergé**, station Linux avec des PMU réelles et éventuellement un GPU. Seul étage qui vérifie qu'un compteur remonte vraiment. Non bloquant, exécuté la nuit.

**Étage 3 - campagnes périodiques sur cluster**, un centre GENCI pour NVIDIA et le passage à l'échelle MPI, LUMI ou équivalent pour AMD. Quelques fois par an, manuelles ou planifiées, et **leur livraison est le rafraîchissement du corpus d'enregistrements**.

### Les trois cas durs

- **La Calibration : on teste des propriétés, jamais des chiffres.** Un Plafond mesuré ne dépasse jamais le pic théorique de la table de microarchitectures ; un Plafond est le **maximum** de ses répétitions et jamais leur moyenne (ticket 05) ; deux Calibrations successives sur la même Machine restent dans une tolérance ; le repli théorique s'active quand le noyau ne peut pas tourner ; la rétrogradation en « estimé » se déclenche en conditions polluées.
- **Le pipeline LLM : le prompt est une fonction pure du pivot**, donc un artefact sous test par capture d'instantané. Tout changement de ce que le modèle voit devient un diff relu en revue. C'est déterministe, presque gratuit, et cela garde la classe de bug la plus dangereuse : envoyer du source sous `--no-source`, envoyer un Hotspot sous le plancher statistique, laisser filer de l'assembleur. Ces trois règles viennent des tickets 07 et 10 et n'étaient garanties par rien d'exécutable. S'y ajoutent la détection obligatoire des erreurs de provider (ticket 08) et l'étiquetage en « conseil ». **La qualité du conseil ne barre aucune fusion** : elle est relue par un humain sur un jeu de cas figés à chaque version.
- **Le rapport** : alimenté par un pivot figé, il produit un HTML déterministe, donc des instantanés sur la sortie, plus quelques parcours de navigateur sur les parties interactives - substitution des vues, mode `--no-source`, cas « hors du roofline » - ce qui tourne sur un runner hébergé gratuit. Et un test unitaire sur la géométrie du roofline, `min(pic, bande passante × intensité)` : c'est exactement le bug introduit dans le prototype du ticket 14, invisible à la lecture du code et évident au rendu.

### Ce qu'on assume de ne pas pouvoir tester

Écrit noir sur blanc plutôt que passé sous silence : la justesse absolue des compteurs sur les microarchitectures qu'on ne possède pas, l'overhead réel à l'échelle, MPI au-delà de ce que les campagnes atteignent, la qualité des conseils, et les ISA et cibles `gfx` hors wheel.

**Ce ne sont pas des trous, ce sont les zones que le produit couvre par son honnêteté plutôt que par ses tests.** `doctor` annonce ce qu'il ne sait pas faire, la Provenance enregistre dans quelles conditions un chiffre a été produit, et la rétrogradation motivée dit pourquoi une valeur est incertaine. Un outil qui ne peut pas tout tester doit **déclarer ce qu'il ne sait pas** - c'est ce que la carte construit depuis le ticket 05, et la stratégie de test en est le dernier maillon.

### Articulation avec la veille de version

Le job de CI décidé au ticket 13, déclenché sur chaque rc et chaque majeure LLVM, **est l'étage 1 appliqué à une nouvelle version d'outil** : il diffe la liste des `-mcpu` et rejoue le corpus. Le même mécanisme couvre tous les outils orchestrés. Corpus de binaires figés et corpus d'enregistrements sont donc les deux actifs durables du projet, et ils servent à la fois la non-régression et la veille.
