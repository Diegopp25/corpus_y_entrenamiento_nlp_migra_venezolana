#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Entrena RoBERTa en español con el pipeline multitarea compartido."""

import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
BETO_DIR = MODEL_DIR.parent / "beto"
sys.path.insert(0, str(BETO_DIR))

from train import main


if __name__ == "__main__":
    main(
        default_model="FacebookAI/xlm-roberta-base",
        default_out_dir=MODEL_DIR / "models",
        default_model_file="roberta_es_multitask.pt",
        default_model_label="RoBERTa español",
    )
