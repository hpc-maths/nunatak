# 07 - Machine et plafonds

Référence : [ADR 0002](../development/decisions/0002-machine-characterisation.md).

Ce qui est construit et documenté a rejoint le site : l'identité d'une
Machine, la calibration et sa rétrogradation en conditions polluées, le
repli théorique et la sonde réseau sont dans
[Machine et plafonds](../guide/machine/index.md) ; les invariants
testables dans [la stratégie de test](../development/testing.md).

## Reste à construire

- **Variante précompilée du noyau de calibration**, sélectionnée par
  dispatch d'ISA à l'exécution (`CPUID` sur x86, `AT_HWCAP` sur ARM),
  au-dessus de la recompilation locale dans l'échelle de repli. Mesurer
  le pic avec des instructions plus étroites que ce que la machine sait
  faire produirait un plafond faux portant l'étiquette `mesuré` : le
  noyau actuel se contente de signaler l'absence de SIMD et rétrograde.
- **`likwid-bench` en raffinement optionnel** quand il est présent,
  jamais en dépendance.
