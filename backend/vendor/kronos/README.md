# Vendored — Kronos

This directory contains the model implementation from
[`shiyu-coder/Kronos`](https://github.com/shiyu-coder/Kronos), vendored so this repo is
self-contained and reproducible at install time (see `doc/plan.md`, Decision log).

| | |
|---|---|
| Upstream | https://github.com/shiyu-coder/Kronos |
| Pinned commit | `67b630e67f6a18c9e9be918d9b4337c960db1e9a` (2026-04-13) |
| Licence | MIT — © 2025 ShiYu, see [`LICENSE`](./LICENSE) |
| Paper | Kronos: A Foundation Model for the Language of Financial Markets (AAAI 2026), [arXiv:2508.02739](https://arxiv.org/abs/2508.02739) |

## What was copied

| Upstream path | Path here |
|---------------|-----------|
| `model/kronos.py` | `kronos.py` |
| `model/module.py` | `kronos_modules.py` |
| `LICENSE` | `LICENSE` |

## Changes applied at vendoring time

Only import plumbing was changed — **no model logic was modified**:

1. `from model.module import *` → `from .kronos_modules import *`, so the module resolves as a
   package rather than depending on the upstream repo layout.
2. Removed `sys.path.append("../")`, which only made sense when running upstream's example scripts
   from inside its own checkout.
3. CRLF line endings normalised to LF.

Note: `kronos_modules.py` is still imported with `*` on purpose — upstream's `kronos.py` relies on
that star import for `nn` and `F`. Renaming it to an explicit import list would be a behavioural
change and is deliberately avoided.

## Weights are not vendored

Checkpoints are downloaded from the Hugging Face Hub on first use
(`NeoQuasar/Kronos-Tokenizer-base`, `NeoQuasar/Kronos-small`, …). Keeping weights out of git is what
makes the repo small; see `doc/objective.md` §5.

## Re-vendoring

```bash
git clone --depth 1 https://github.com/shiyu-coder/Kronos.git /tmp/kronos_ref
cp /tmp/kronos_ref/model/module.py  backend/vendor/kronos/kronos_modules.py
cp /tmp/kronos_ref/model/kronos.py  backend/vendor/kronos/kronos.py
cp /tmp/kronos_ref/LICENSE          backend/vendor/kronos/LICENSE
sed -i 's/\r$//' backend/vendor/kronos/*.py
# then re-apply the two import changes listed above and update the pinned commit in this table
```
