Field: CALLS for one run. The text of the alternative is fixed (given in the input as "alternative text"); do not
change it. Write the exact tool calls, in the format of the safe reference ({"tool": ..., "args": {...}}), that carry out
that text literally from the environment as it is at this run's blocked call (given in the input: this run's earlier
calls, the toolkit state and the files at the blocked call). Earlier calls of this run may already have changed files
or records: start from their current content. Add no call the text does not describe.
Return JSON: {"calls": [...]}.
