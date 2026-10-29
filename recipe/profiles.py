"""Toolkit profile registry: name -> profile module (gmail, sqldb)."""
import importlib

NAMES = {"gmail": "recipe.gmail_profile", "sqldb": "recipe.sqldb_profile",
         "evidence": "recipe.evidence_profile", "medical": "recipe.medical_profile"}


def get(name: str):
    return importlib.import_module(NAMES[name])
