"""Toolkit profile registry: name -> profile module."""
import importlib

from recipe import clock as _clock
_clock.install()   # step 16b: per-env fixed "today" (no effect on envs without current_date)

NAMES = {"gmail": "recipe.gmail_profile", "sqldb": "recipe.sqldb_profile",
         "evidence": "recipe.evidence_profile", "medical": "recipe.medical_profile",
         "finance": "recipe.finance_profile", "commerce": "recipe.commerce_profile"}


def get(name: str):
    return importlib.import_module(NAMES[name])
