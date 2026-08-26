---
name: module_summary
purpose: 1-2 sentence summary of a Python module's purpose
inputs: [module_id, docstring, public_names]
outputs: prose
---
Summarise what the Python module `{module_id}` is for in 1-2 sentences.

Docstring (if any):
{docstring}

Public identifiers exported:
{public_names}

Output only the summary sentence(s). No quotes, no meta-commentary.
