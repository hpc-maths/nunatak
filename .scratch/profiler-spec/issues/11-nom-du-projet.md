# Décision : nom du projet

Type: grilling
Status: resolved

## Question

Quel nom pour la librairie et le paquet (PyPI, dépôt public, commande CLI) ?

Contraintes : disponible sur PyPI et comme nom de dépôt, prononçable, évoque le profiling/la performance, pas de collision avec les outils existants du domaine (likwid, maqao, tau, hpctoolkit, scalene...). Vérifier la disponibilité avant de trancher.

## Answer

**`nunatak`** - un sommet rocheux qui émerge au-dessus de la calotte glaciaire, c'est-à-dire ce qui dépasse du bruit. La commande devient `nunatak run -- mpirun ./app`, et le placeholder `profiler` a été remplacé partout dans la spec.

**Disponibilité vérifiée** (index officiel PyPI, pas l'API JSON qui donne des faux positifs) : `nunatak` libre sur PyPI, sur npm et sur Homebrew, aucun paquet Debian, aucun binaire de ce nom. 13 dépôts GitHub le portent, le plus visible à 2 étoiles. Aucun outil de profilage, aucune collision avec likwid, maqao, tau, hpctoolkit ou scalene.

**Candidats écartés, et pourquoi.** `headroom` et `crux` étaient les deux meilleures idées sémantiques (l'espace sous le plafond, le passage-clé d'une voie) : pris sur PyPI et massivement occupés sur GitHub. `arete`, `crest`, `gable`, `cairn`, `beacon`, `capstone`, `summit`, `ceiling`, `skyline` : tous pris. `ridgeline`, qui aurait été le meilleur choix sémantique puisque le *ridge point* est le terme canonique de l'article de 2009, est **disqualifié par un homonyme direct** : un « small roofline profiler for LLM inference » existe déjà sous ce nom, et « ridgeline plot » désigne par ailleurs un type de graphique. `roofline` est libre sur PyPI mais s'approprie le nom d'un modèle publié et rétrécit le produit à une seule de ses fonctions. `cuesta` a été écarté après vérification : en espagnol courant, le mot signifie « ça coûte ». `esker`, un temps retenu, a été abandonné au terme de la vérification approfondie : le paquet PyPI est libre et aucun outil du domaine ne porte ce nom, mais **Esker S.A. est une société de logiciel française cotée** qui détient `esker.com`, `esker.fr`, le compte GitHub `esker`, le paquet npm et les domaines `.dev` et `.io`. Rien n'empêchait de publier, mais toute la surface publique du nom appartenait déjà à quelqu'un d'autre, dans la même catégorie et la même juridiction.

**Identité visuelle** dans `docs/brand/`. La silhouette de la marque est le roofline lui-même : flanc gauche en diagonale (régime limité par la mémoire), sommet plat (plafond de calcul), point de rupture marqué en accent chaud, et une nappe de glace qui coupe le massif en laissant deviner la masse immergée - ce qui n'est pas mesuré. Cinq fichiers : marque couleur fond clair et fond sombre, monochrome en `currentColor`, variante réduite pour 24 px et moins, et lock-up avec mot-symbole en chasse fixe. Réserve : le mot-symbole du lock-up est encore du texte vivant et doit être vectorisé avant diffusion.
