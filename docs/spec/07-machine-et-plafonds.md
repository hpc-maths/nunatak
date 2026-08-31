# 07 - Machine et plafonds

Référence : [ADR 0002](../development/decisions/0002-machine-characterisation.md).

## Identité d'une Machine

**Une Machine n'est pas un nœud.** Son identité est un couple **matériel + forme d'allocation** : deux jobs recevant des parts différentes du même nœud sont deux Machines, et mille nœuds identiques d'un cluster n'en sont qu'une.

Cette définition est ce qui rend les Plafonds comparables aux Mesures : un Plafond vaut pour un périmètre donné - celui de l'allocation - et se compare à des Mesures agrégées sur ce même périmètre. Comparer une mesure faite sur 8 cœurs à un plafond mesuré sur 128 est une faute que cette définition rend impossible.

La Machine est **partagée et mise en cache entre Runs**, et chaque Run en embarque un **instantané complet** dans son manifeste. Le cache peut disparaître sans qu'aucun Run n'y perde quoi que ce soit.

## Calibration

L'opération qui produit les Plafonds en exécutant des microbenchmarks sur la cible.

- **Déclenchée une fois par Machine**, au premier Run, mise en cache, jamais rejouée sans raison. Exposée aussi en commande explicite pour qui veut la faire dans un petit job dédié plutôt qu'au début d'une grosse allocation.
- **Un Plafond est le maximum de ses répétitions, jamais leur moyenne** : on cherche une borne supérieure.
- Exécutée dans un **processus autonome**, pas depuis l'interpréteur Python : la calibration cherche une borne supérieure, et la mesurer avec l'interpréteur résident, son allocateur et son ramasse-miettes polluerait précisément la grandeur visée.
- **Conditions polluées** (charge concurrente détectée, fréquence instable, allocation partagée) : les Plafonds obtenus sont rétrogradés en `estimé` avec la raison.

## Échelle de repli

Dans cet ordre :

1. **variante précompilée** du noyau de calibration, sélectionnée par dispatch d'ISA à l'exécution (`CPUID` sur x86, `AT_HWCAP` sur ARM) ;
2. **recompilation locale** depuis les sources embarquées - il y a toujours un compilateur sur un cluster ;
3. **table théorique de microarchitectures**, avec Qualité `estimé`.

Le dispatch d'ISA n'est pas cosmétique : mesurer le pic avec des instructions plus étroites que ce que la machine sait faire produirait un plafond faux portant l'étiquette `mesuré`, ce qui est pire qu'un plafond estimé.

## Plafonds à produire

| Plafond | Source |
|---|---|
| Pic FLOP/s par précision | noyau de calibration |
| Bande passante par niveau de la hiérarchie mémoire | noyau de calibration |
| Bande passante réseau | sonde réseau construite localement |

`likwid-bench` reste un **raffinement optionnel** quand il est présent, jamais une dépendance.

## macOS

Le ticket 02 a établi qu'Apple Silicon n'expose ni compteur FLOPs ni bande passante DRAM. La Calibration y produit donc des Plafonds par microbenchmark comme ailleurs, mais **le placement des Hotspots sur ces plafonds reste estimé**, l'intensité arithmétique venant de l'analyse statique (chapitre 08) et non des compteurs.

## Invariants testables

- un Plafond mesuré ne dépasse jamais le pic théorique de la table de microarchitectures ;
- un Plafond est le maximum de ses répétitions ;
- deux Calibrations successives sur la même Machine restent dans une tolérance ;
- le repli théorique s'active quand le noyau ne peut pas tourner ;
- la rétrogradation en `estimé` se déclenche en conditions polluées.

**On teste des propriétés, jamais des chiffres** : la valeur d'un Plafond *est* la machine ([stratégie de test](../development/testing.md)).
