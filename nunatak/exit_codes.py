"""Reserved exit codes, in the manner of `timeout` and `env`.

The application's exit code is propagated in the general case: nunatak
observes, it never masks. An application exiting with 125 itself is
indistinguishable from a nunatak failure; that ambiguity is the documented
price of transparency, and the JSON output settles it when certainty is
needed.
"""

COMMAND_NOT_FOUND = 127
COMMAND_NOT_EXECUTABLE = 126
FAILURE_BEFORE_LAUNCH = 125
STRICT_VIOLATION = 121
