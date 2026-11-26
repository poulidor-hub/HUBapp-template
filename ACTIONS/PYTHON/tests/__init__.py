# SPDX-License-Identifier: MIT
# Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

"""Paquet de tests ACTIONS/PYTHON.

Rend pytest collectable en une seule invocation aux côtés de
`test_allocate_ports.py` (à la racine) : sans `__init__.py`, les deux
fichiers de même basename entrent en collision (« import file mismatch »).
"""
