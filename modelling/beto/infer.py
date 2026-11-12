#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T-01 · Inferencia con el modelo final (models_beto/beto_multitask.pt).

Uso:
    python infer.py --text "Texto de una noticia..."
    python infer.py --csv noticias.csv --text_col Cuerpo --out predicciones.csv
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer

from preprocess import prepare_text
from train import DEFAULT_MODEL, MultiTaskBETO

T_DIR = Path(__file__).resolve().parent
DEFAULT_CKPT = T_DIR / "models_beto" / "beto_multitask.pt"


def load_model(ckpt_path, device, model_name=None):
    ckpt = torch.load(ckpt_path, map_location=device)

    name = ckpt.get("model_name") or model_name or DEFAULT_MODEL
    model = MultiTaskBETO(name, n_labels=len(ckpt["label_cols"])).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained(name)
    return model, tokenizer, ckpt


@torch.no_grad()
def predict_texts(texts, model, tokenizer, ckpt, device, max_len=None, batch_size=8):
    """Devuelve un DataFrame: sentimiento, p_<sentimiento>, <tema> (0/1) y p_<tema>."""
    max_len = max_len or ckpt.get("max_len", 512)
    id2sent = {v: k for k, v in ckpt["sent_map"].items()}
    cols = ckpt["label_cols"]
    thr = np.array([ckpt["thresholds"][c] for c in cols])

    texts = [prepare_text(t) for t in texts]
    rows = []

    for i in range(0, len(texts), batch_size):
        enc = tokenizer(
            texts[i : i + batch_size],
            truncation=True,
            max_length=max_len,
            padding=True,
            return_tensors="pt",
        ).to(device)

        s_logit, l_logit = model(enc["input_ids"], enc["attention_mask"])
        s_probs = torch.softmax(s_logit, dim=-1).cpu().numpy()
        l_probs = torch.sigmoid(l_logit).cpu().numpy()

        for sp, lp in zip(s_probs, l_probs):
            row = {"sentimiento": id2sent[int(sp.argmax())]}
            for k in sorted(id2sent):
                row[f"p_{id2sent[k]}"] = float(sp[k])
            for k, c in enumerate(cols):
                row[c] = int(lp[k] >= thr[k])
            for k, c in enumerate(cols):
                row[f"p_{c}"] = float(lp[k])
            rows.append(row)

    return pd.DataFrame(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt", default=str(DEFAULT_CKPT))
    p.add_argument("--text", help="Un solo texto")
    p.add_argument("--csv", help="CSV con textos")
    p.add_argument("--text_col", default="Cuerpo")
    p.add_argument("--out", default="predicciones.csv")
    p.add_argument("--batch_size", type=int, default=8)
    args = p.parse_args()

    if not args.text and not args.csv:
        raise SystemExit("Indica --text o --csv")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, tokenizer, ckpt = load_model(args.ckpt, device)

    if args.text:
        preds = predict_texts([args.text], model, tokenizer, ckpt, device)
        print(preds.iloc[0].to_string())
        return

    df = pd.read_csv(args.csv, encoding="utf-8-sig")
    texts = df[args.text_col].fillna("").astype(str).tolist()
    preds = predict_texts(texts, model, tokenizer, ckpt, device, batch_size=args.batch_size)

    out = pd.concat([df.reset_index(drop=True), preds], axis=1)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"Predicciones guardadas en: {args.out}")


if __name__ == "__main__":
    main()
