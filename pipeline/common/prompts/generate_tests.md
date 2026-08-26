---
name: generate_tests
purpose: write pytest tests that assert observable behavior for one module
inputs: [module_path, module_source]
outputs: pytest_source
---
You are helping build a coverage-improving test suite for the module at
{module_path}.

Rules:
- Every test asserts a real observable output — a return value, a raised
  exception, a mutated argument. Tests that merely call a function are
  rejected downstream.
- Use pytest, no unittest.
- Cover the module's public functions. Avoid trivial getters.
- If the module raises on invalid input, add a test using pytest.raises.
- One test file, importable as `test_<module_stem>_gen`.

Module source:
```python
{module_source}
```

Output only the pytest source — no prose, no fences.
