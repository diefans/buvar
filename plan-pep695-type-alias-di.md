# Plan: Support PEP 695 `type X = Any` Aliases in DI

## 0. Solved Projection

**Done means:** `~/code/bm/ucm` (after its change `ApiConfig = Any` → `type ApiConfig = Any`)
runs its full test suite green against buvar, and buvar carries a regression
test that fails on the pre-fix code and passes after it.

Authoritative reference: downstream consumer `bm/ucm` `src/bm/ucm/config.py`
(`type ApiConfig = Any`, then `ApiConfigs = dict[ApiProvider, dict[ApiFlavor, ApiConfig]]`
registered via `di.register(resolve_api_configs)`).

Observable success:
- `bm/ucm` `tests/test_api_configs.py` — 4 passed (currently 2 failed / 1 passed / 1 error).
- `bm/ucm` full suite — 656 passed (observed with the patched buvar).
- `buvar` `tests/test_di.py::test_nject_pep695_type_alias` — passes with fix, fails without.

Current gap count: 1 buvar defect (`BaseMatrix.__call__` returns `None` for a
`typing.TypeAliasType`, crashing registration); 1 downstream regression.

## Table of Contents

- [0. Solved Projection](#0-solved-projection)
- [1. General Problem Map](#1-general-problem-map)
- [2. Adjacent Boundaries](#2-adjacent-boundaries)
- [3. Work Slices](#3-work-slices)
  - [Slice 1 — BaseMatrix: treat PEP 695 alias as atomic leaf](#slice-1--basematrix-treat-pep-695-alias-as-atomic-leaf)
  - [Slice 2 — Regression test in buvar](#slice-2--regression-test-in-buvar)
  - [Slice 3 — README currency](#slice-3--readme-currency)
  - [Slice 4 — Downstream integration verification](#slice-4--downstream-integration-verification)
- [4. Dependency Graph](#4-dependency-graph)
- [5. Verification](#5-verification)
- [6. Change Log](#6-change-log)

---

## 1. General Problem Map

```
ucm:  type ApiConfig = Any                       (PEP 695, py>=3.12)
      ApiConfigs = dict[str, dict[str, ApiConfig]]
              │
              ▼  di.register(resolve_api_configs)   (buvar)
      ┌───────────────────────────────────────────────────────────┐
      │ buvar/di/__init__.py                                      │
      │   CallableAdapter.return_type() -> ApiConfigs             │
      │        │                                                  │
      │        ▼                                                  │
      │   BaseMatrix.__call__(ApiConfigs)            [GREEN]      │
      │     ti.is_generic_type -> iter_generic                    │
      │        get_args -> (str, dict[str, ApiConfig])            │
      │        for each arg: self(arg)                            │
      │           dict[str, ApiConfig] -> iter_generic            │
      │             get_args -> (str, ApiConfig)                  │
      │                self(ApiConfig)               [RED]        │
      │                  isclass?   no                             │
      │                  optional?  no                             │
      │                  tuple?     no                             │
      │                  union?     no                             │
      │                  generic?   no  -> returns None            │
      │             it.product(*map(self, args)) -> product(None)  │
      │                  TypeError: 'NoneType' object not iterable │
      └───────────────────────────────────────────────────────────┘

Root cause:  typing.TypeAliasType (the object behind `type X = ...`) is none
             of the recognised kinds, so BaseMatrix.__call__ implicitly
             returns None. iter_generic feeds that None to itertools.product.

Additional fact (drives the fix choice):
  dict[str, dict[str, ApiConfig]] != dict[str, dict[str, Any]]   (hash differs)
  -> unwrapping the alias to __value__ would ALSO break lookup, because
     registration key and nject target must be the same object/equal key.
     => Register/lookup the alias itself as an opaque leaf (symmetric).
```

### Context — what's already in place

| Feature | Status |
|---|---|
| `BaseMatrix` over class/optional/tuple/union/generic | ✅ Implemented |
| Generic alias return types (e.g. `list[Foo]`, `dict[str, Foo]`) | ✅ Implemented + tested (`test_adapter.py`) |
| `type X = ...` (PEP 695 `TypeAliasType`) handling | ❌ Missing — falls through to `None` |
| ucm `type ApiConfig = Any` consumer | ❌ Broken by the missing handling |
| Cython `c_di` path | ✅ Implements only resolve/nject; uses same Python `BaseMatrix`/`Adapter` |

## 2. Adjacent Boundaries (NOT touched by any slice)

| Domain | Reason |
|---|---|
| `src/buvar/di/c_di.pyx` | Compiled implementation only mirrors resolve/nject; `BaseMatrix` and `Adapter` classes live in `di/__init__.py` and are shared. |
| `src/buvar/di/py_di.py` | Pure-Python resolve path; uses the same shared `Adapter`/`BaseMatrix`. |
| `src/buvar/components/**` | Component registry is unrelated to type-matrix registration. |
| `di.evaluate()` `_eval_type` deprecation (line 163) | Separate latent 3.15 issue (missing `type_params`); not on the projection. See Change Log note. |
| `bm/ucm` source | Consumer is the *trigger*, not the fix site; its `config.py` change is already made and must stay. |

## 3. Work Slices

### Slice 1 — BaseMatrix: treat PEP 695 alias as atomic leaf

Domain: buvar dependency injection (type matrix).

Files touched:
- MOD `src/buvar/di/__init__.py`

Problem details:
- `BaseMatrix.__call__` has no branch for `typing.TypeAliasType`; it returns
  `None`, and `iter_generic`'s `it.product(*map(self, args))` raises
  `TypeError: 'NoneType' object is not iterable` during `register()`.
- Aliases must be registered *and* looked up as themselves (they are not
  equal to their unwrapped value when nested in a generic), so unwrapping is
  not an option.

Design rationale:
- Add an explicit terminal branch returning `iter((tp,))` for
  `isinstance(tp, t.TypeAliasType)`. This is symmetric with lookup
  (`GenericAdapter.lookup` does exact registry-key matching), minimal, and
  preserves the current fail-fast `None` for genuinely unknown types.
- Alternative considered (broader): an unconditional fallback
  `return iter((tp,))` for any unrecognised leaf (`Literal`, `TypeAliasType`,
  …). More future-proof but silently masks unknown constructs; rejected per
  Principle 3 (minimum complexity) + fail-fast preference.

Internal map:
```
class BaseMatrix:
    def __call__(self, tp):
        if inspect.isclass(tp): ...
        if ti.is_optional_type(tp): ...
        if ti.is_tuple_type(tp): ...
        if ti.is_union_type(tp): ...
        if ti.is_generic_type(tp): ...
+       if isinstance(tp, t.TypeAliasType):
+           # PEP 695 `type X = ...`: not equal to its value when nested,
+           # so register/lookup the alias object itself.
+           return iter((tp,))
```

Adjacent boundaries (NOT touched):
- `Adapter` metaclass + `GenericAdapter.register/lookup` (no change needed).
- `c_di.pyx` / `py_di.py`.

Dependencies: None.

TODOs:
- [x] Add the `isinstance(tp, t.TypeAliasType)` branch in `BaseMatrix.__call__`.
- [x] Comment explains the non-equality constraint (why not unwrap).

### Slice 2 — Regression test in buvar

Domain: buvar test suite.

Files touched:
- MOD `tests/test_di.py`

Problem details:
- No test covers PEP 695 aliases; this is why the regression reached ucm.

Design rationale:
- One focused test mirroring ucm's exact shape (alias to `Any` nested two
  dict levels), added next to the other `test_nject_*` cases. Fails on
  pre-fix code with the `NoneType` TypeError; passes after Slice 1.

Internal map:
```
async def test_nject_pep695_type_alias(adapters):
    from typing import Any
    type ApiConfig = Any
    ApiConfigs = dict[str, dict[str, ApiConfig]]
    async def adapt() -> ApiConfigs:
        return {"provider": {"flavor": {"userinfo_url": "/u"}}}
    adapters.register(adapt)
    assert await adapters.nject(ApiConfigs) == {...}
```

Adjacent boundaries (NOT touched):
- Existing `test_di.py` cases (unchanged).
- `test_adapter.py` (generic/optional coverage already present).

Dependencies: Requires Slice 1.

TODOs:
- [x] Add `test_nject_pep695_type_alias` to `tests/test_di.py`.
- [x] Confirm it fails against unpatched `di/__init__.py` (red) and passes after Slice 1 (green).

### Slice 3 — README currency

Domain: buvar docs (Principle 9).

Files touched:
- MOD `README.rst`

Problem details:
- README documents DI adapters but not the set of supported registration/
  lookup key kinds; PEP 695 aliases are now supported and should be stated.

Adjacent boundaries (NOT touched):
- `CHANGELOG.md` (generated by commitizen on release).

Dependencies: Requires Slice 1.

TODOs:
- [x] Note PEP 695 `type X = ...` alias support in the DI/adapters section.

### Slice 4 — Downstream integration verification

Domain: buvar ↔ ucm integration (offline replication + operator live check).

Files touched: None (verification only).

Problem details:
- The projection is defined by ucm's suite going green. Agent verifies
  offline by running ucm's suite against the fixed buvar; operator confirms
  on their normal environment / after a buvar release.

Adjacent boundaries (NOT touched):
- `bm/ucm/src/bm/ucm/config.py` (the trigger change stays as-is).

Dependencies: Requires Slices 1 and 2.

TODOs:
- [x] Offline: run ucm `tests/test_api_configs.py` → 4 passed (observed).
- [x] Offline: run ucm full `tests` → 656 passed (observed).
- [ ] Operator: confirm ucm green in their environment / after buvar release.

## 4. Dependency Graph

```
Slice 1 ──┬──► Slice 2 ──┐
          ├──► Slice 3   │
          │              ▼
          └──────────► Slice 4   (needs 1 + 2)
```

Slices 2 and 3 are independent of each other; both require Slice 1.
Slice 4 is the acceptance gate for Slice 1 + 2.

## 5. Verification

Criteria every slice must pass (offline — Principle 21):

1. `ruff check` and `ruff format --check` — no findings (Principle 26).
2. `buvar` tests: `.devenv/state/venv/bin/python -m pytest tests -q` → 154 passed, 2 xfailed (baseline) **+ 1 new test**.
3. Sliced acceptance (offline): ucm suite vs patched buvar →
   - `tests/test_api_configs.py` → 4 passed
   - full `tests` → 656 passed
   Command form used:
   `PYTHONPATH=<patched buvar> .devenv/state/venv/bin/python -m pytest tests -q --no-cov`
4. Code review — matches slice TODOs.

No hardware/live integration; Slice 4 operator confirmation is the only
non-offline check.

## 6. Change Log

| Date | Change | Source |
|---|---|---|
| 2026-10-06 | Initial plan created | Reproduced ucm failure; bisected to `BaseMatrix.__call__`; validated fix + test in `/tmp/opencode/` sandbox on ucm 3.14.6 env |
| 2026-10-06 | Chose explicit `TypeAliasType` branch over broad leaf fallback | Both validated (656/154 green); minimum-complexity + fail-fast |
| 2026-10-06 | Noted `evaluate()` `_eval_type` 3.15 deprecation as out-of-scope adjacent issue | Observed warning during repro |
```

### Evidence (sandbox, offline)

| Check | Pre-fix | Post-fix |
|---|---|---|
| `ucm tests/test_api_configs.py` | 2 failed, 1 passed, 1 error | 4 passed |
| `ucm tests` (full) | — | 656 passed |
| `buvar tests` (full) | 154 passed, 2 xfailed | 154 passed, 2 xfailed |
| `test_nject_pep695_type_alias` | failed (TypeError) | passed |
