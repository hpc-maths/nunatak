# 02 - Modèle de domaine

Le glossaire de référence est [`docs/reference/glossary.md`](../reference/glossary.md). Il est **contraignant** : ces mots s'emploient tels quels dans le code, les messages de l'interface, le rapport et la documentation, et les termes proscrits qu'il liste ne s'emploient nulle part. Ce chapitre donne les relations et les invariants ; il ne recopie pas les définitions.

## Les entités et leurs liens

```
Run ─┬─ Machine (partagée, mise en cache entre Runs)
     │     └─ Plafond*        (porte une Qualité)
     ├─ Provenance             (code, dépendances, configuration effective)
     ├─ Passe*
     ├─ Hotspot* ─┬─ identité physique   (natif uniquement)
     │            ├─ identité logique
     │            ├─ Niveau de résolution
     │            └─ détail interne : lignes, chaîne d'inlining
     ├─ Locus*    (nœud > rang > thread, ou nœud > device > stream)
     ├─ Mesure*   (Hotspot × Locus, porte Qualité, échantillons, Passe)
     │     └─ Compteur brut | Métrique dérivée (Linéage)
     └─ Événement*
```

Recalculés à la demande, **jamais persistés** : le Diagnostic, l'Analyse statique de boucle, tout agrégat entre Loci.
Persistée à part, régénérable sans reprofiler : l'Explication.

## Invariants

Ces règles sont vérifiables et doivent être testées ([stratégie de test](../development/testing.md)).

**I1. Le pivot mesuré ne contient aucune conclusion.** Un Run porte des Hotspots, des Loci, des Mesures et des Événements. Il ne porte ni classification, ni placement roofline, ni conseil. Tout cela se recalcule.

**I2. Aucune agrégation entre Loci n'est stockée.** Somme, moyenne, minimum, maximum et déséquilibre se calculent à la demande. Stocker un agrégat, c'est figer une question qu'on n'a pas encore posée.

**I3. Aucune adresse absolue n'est persistée.** Toute adresse est normalisée dès l'ingestion en `(identité de module, offset)`. C'est ce qui fait tomber l'ASLR et le réordonnancement de fonctions, et ce qui fait converger vers un même Hotspot des rangs ayant chargé une bibliothèque à des adresses différentes.

**I4. La Qualité d'une Métrique dérivée est la pire de ses entrées**, propagée automatiquement le long du Linéage. Elle ne se fixe jamais à la main.

**I5. Une Métrique dérivée ne peut combiner des Compteurs bruts de Passes différentes que si l'identité physique de leur module est identique dans ces Passes.** Sinon, refus - pas de rétrogradation ([comment lire ce que nunatak dit](../guide/reading-what-nunatak-tells-you.md)).

**I6. L'Analyse statique de boucle ne produit jamais la Qualité « mesuré ».** C'est un modèle, pas une mesure de la machine.

**I7. Les deux intensités arithmétiques ne se substituent jamais l'une à l'autre.** L'intensité DRAM vient des compteurs, l'intensité L1 de l'analyse statique. Toute mention précise laquelle.

**I8. Un Run est un seul répertoire**, quel que soit le nombre de rangs.

## Identité d'un Hotspot

Deux identités, deux usages, jamais confondues.

| | Composition | Sert à |
|---|---|---|
| **Physique** | `(build-id \| LC_UUID, offset)` | agréger dans un Run, valider les fusions inter-passes |
| **Logique** | `(module, nom démanglé, fichier source)` | afficher, alimenter le modèle, comparer entre Runs |

La **ligne de déclaration est un attribut, jamais une composante de clé** : l'y mettre ferait basculer chaque fonction sur une nouvelle identité dès qu'on ajoute trois lignes en haut d'un fichier, et la comparaison entre Runs s'effondrerait sur une édition triviale.

L'identité logique se transpose sans modification au GPU, `(module, nom de kernel démanglé)`, et à Python, `(fichier .py, nom de fonction)`. **Seul le natif possède une identité physique.**

## Persistance

Format retenu (ADR 0001) : **Parquet** pour le pivot mesuré, **JSON** pour le manifeste.

Le manifeste porte : l'instantané complet de la Machine et de ses Plafonds, la Provenance, la liste des Passes, la configuration effective, et les dégradations rencontrées. Il doit être lisible **sans nunatak** : c'est ce qui rend un Run archivable à dix ans.

L'Explication est persistée dans un fichier séparé du pivot. Supprimer ce fichier ne perd aucune mesure.
