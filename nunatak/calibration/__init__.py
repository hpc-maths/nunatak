"""Calibration: the operation that produces the Ceilings of a Machine.

The nominal path runs microbenchmarks on the target - a Ceiling is the
maximum of its repetitions, never their mean, because a roofline only
makes sense against a bound that is reachable in practice. The
theoretical table is the last rung of the fallback ladder: it never
produces anything better than an estimated Ceiling, and it never
extrapolates - an unknown microarchitecture yields no Ceiling at all.
"""
