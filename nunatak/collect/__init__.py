"""Collection orchestration: adapters around external collectors.

Every collector is executed as a subprocess and its output parsed, never
linked: the product's license and ABI stay decoupled from every tool's.
The single execution boundary lives
in `execution.py`; it is what the corpus records and replays.
"""
