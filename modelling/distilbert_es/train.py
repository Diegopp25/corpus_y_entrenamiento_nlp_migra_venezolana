#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Entrena DistilBERT en español con el pipeline multitarea compartido."""

import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
BETO_DIR = MODEL_DIR.parent / "beto"
sys.path.insert(0, str(BETO_DIR))

from train import main


if __name__ == "__main__":
    main(
        default_model="dccuchile/distilbert-base-spanish-uncased",
        default_out_dir=MODEL_DIR / "models",
        default_model_file="distilbert_es_multitask.pt",
        default_model_label="DistilBERT español",
    )
