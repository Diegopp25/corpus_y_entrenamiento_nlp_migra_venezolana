#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T-01 · BETO multitarea (sentimiento + temas).

- BETO (bert-base-spanish-wwm-cased) con dos cabezas
- Pesos de clase para sentimiento y pos_weight para labels multilabel
- Early stopping por Macro-F1 de temas
- Threshold óptimo por etiqueta (sobre OOF)
- Selección del mejor fold y epoch para el modelo final

Uso:
    python train.py                  # cv + final (igual que el script original)
    python train.py --stage cv       # CV -> thresholds y checkpoint del mejor fold
    python train.py --stage final    # guarda el mejor checkpoint (requiere etapa cv)
"""

import argparse
import gc
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import precision_recall_curve, precision_recall_fscore_support
from tqdm.auto import tqdm
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

from preprocess import (
    DEFAULT_DATA,
    LABEL_COLS,
    SENT2ID,
    describe,
    load_data,
    make_loader,
    make_splits,
    compute_loss_weights,
)

T_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = "dccuchile/bert-base-spanish-wwm-cased"
DEFAULT_MODEL_FILE = "beto_multitask.pt"


def parse_args(
    default_model=DEFAULT_MODEL,
    default_out_dir=T_DIR / "models_beto",
    default_model_file=DEFAULT_MODEL_FILE,
    default_model_label="BETO",
):
    p = argparse.ArgumentParser()

    p.add_argument("--stage", choices=["cv", "final", "all"], default="all")

    p.add_argument("--data", default=str(DEFAULT_DATA))
    p.add_argument("--text_col", default="Cuerpo")
    p.add_argument("--out_dir", default=str(default_out_dir))
    p.add_argument("--model_name", default=default_model)
    p.add_argument("--model_file", default=default_model_file)
    p.add_argument("--model_label", default=default_model_label)

    p.add_argument("--max_len", type=int, default=512)
    p.add_argument("--n_folds", type=int, default=5)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch_size", type=int, default=2)
    p.add_argument("--grad_accum", type=int, default=2)

    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--head_lr", type=float, default=1e-4)
    p.add_argument("--warmup_ratio", type=float, default=0.1)
    p.add_argument("--weight_decay", type=float, default=0.01)
    p.add_argument("--label_loss_weight", type=float, default=1.5)

    p.add_argument("--patience", type=int, default=4)
    p.add_argument("--seed", type=int, default=44)
    return p.parse_args()


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# =========================================================
# MODELO
# =========================================================

class MultiTaskBETO(nn.Module):
    """Encoder + cabeza de sentimiento (3 clases) + cabeza de temas (multilabel).

    Sirve con cualquier encoder de HF; si no hay pooler_output usa el token [CLS].
    """

    def __init__(self, model_name, n_sent=3, n_labels=len(LABEL_COLS), dropout=0.3):
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(dropout)

        self.sent_head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden, n_sent)
        )
        self.label_head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden, n_labels)
        )

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)

        if hasattr(out, "pooler_output") and out.pooler_output is not None:
            pooled = out.pooler_output
        else:
            pooled = out.last_hidden_state[:, 0]

        pooled = self.dropout(pooled)

        return self.sent_head(pooled), self.label_head(pooled)


# =========================================================
# THRESHOLDS Y MÉTRICAS
# =========================================================

def find_best_thresholds(y_true, probs):
    thresholds = {}

    for j, col in enumerate(LABEL_COLS):
        precision, recall, thr = precision_recall_curve(y_true[:, j], probs[:, j])
        f1 = 2 * precision * recall / (precision + recall + 1e-12)
        best_idx = np.argmax(f1[:-1])
        thresholds[col] = float(thr[best_idx])

    return thresholds


def apply_thresholds(probs, thresholds):
    pred = np.zeros_like(probs, dtype=np.int32)

    for j, col in enumerate(LABEL_COLS):
        pred[:, j] = (probs[:, j] >= thresholds[col]).astype(int)

    return pred


def evaluate_predictions(pred, label_thresholds):
    sent_pred = pred["sent_probs"].argmax(1)
    label_pred = apply_thresholds(pred["label_probs"], label_thresholds)

    rows = []

    for task, yt, yp in [
        ("sent", pred["sent_true"], sent_pred),
        ("label", pred["label_true"], label_pred),
    ]:
        for avg in ("macro", "micro"):
            p, r, f, _ = precision_recall_fscore_support(yt, yp, average=avg, zero_division=0)
            rows.append([task, avg, p, r, f])

    metrics = pd.DataFrame(rows, columns=["task", "average", "precision", "recall", "f1"])
    return metrics, sent_pred, label_pred


# =========================================================
# ENTRENAMIENTO
# =========================================================

def _unpack(batch, device):
    return (
        batch["input_ids"].to(device),
        batch["attention_mask"].to(device),
        batch["sent"].to(device),
        batch["labels"].to(device),
    )


@torch.no_grad()
def predict(model, loader, device):
    model.eval()

    s_logits, l_logits, s_true, l_true = [], [], [], []

    for batch in loader:
        ids, mask, sent, labels = _unpack(batch, device)
        s_logit, l_logit = model(ids, mask)

        s_logits.append(s_logit.cpu())
        l_logits.append(l_logit.cpu())
        s_true.append(sent.cpu())
        l_true.append(labels.cpu())

    return {
        "sent_probs": torch.softmax(torch.cat(s_logits), dim=-1).numpy(),
        "label_probs": torch.sigmoid(torch.cat(l_logits)).numpy(),
        "sent_true": torch.cat(s_true).numpy(),
        "label_true": torch.cat(l_true).numpy().astype(int),
    }


def train_one_fold(model, train_loader, val_loader, train_df, device, args):
    sentiment_weights, label_pos_weights = compute_loss_weights(train_df)
    ce = nn.CrossEntropyLoss(
        weight=torch.as_tensor(sentiment_weights, device=device)
    )
    bce = nn.BCEWithLogitsLoss(
        pos_weight=torch.as_tensor(label_pos_weights, device=device)
    )

    enc_params, head_params = [], []
    for name, p in model.named_parameters():
        (enc_params if "encoder" in name else head_params).append(p)

    optimizer = torch.optim.AdamW(
        [
            {"params": enc_params, "lr": args.lr},
            {"params": head_params, "lr": args.head_lr},
        ],
        weight_decay=args.weight_decay,
    )

    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * args.warmup_ratio),
        num_training_steps=total_steps,
    )

    use_amp = torch.cuda.is_available()
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    best_f1 = -1
    patience = 0
    best_state = None
    best_epoch = 0

    for epoch in range(args.epochs):
        model.train()
        losses = []

        pbar = tqdm(train_loader, leave=False)
        optimizer.zero_grad()

        for step, batch in enumerate(pbar):
            ids, mask, sent, labels = _unpack(batch, device)

            with torch.cuda.amp.autocast(enabled=use_amp):
                sent_logits, label_logits = model(ids, mask)
                loss_sent = ce(sent_logits, sent)
                loss_label = bce(label_logits, labels)
                loss = loss_sent + args.label_loss_weight * loss_label

            scaler.scale(loss).backward()

            if (step + 1) % args.grad_accum == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad()

            losses.append(loss.item())

        print(f"epoch {epoch+1}/{args.epochs} | train_loss={np.mean(losses):.4f}")

        val_pred = predict(model, val_loader, device)
        thrs = find_best_thresholds(val_pred["label_true"], val_pred["label_probs"])
        metrics, _, _ = evaluate_predictions(val_pred, thrs)

        current_f1 = float(
            metrics[(metrics.task == "label") & (metrics.average == "macro")]["f1"].iloc[0]
        )

        if current_f1 > best_f1:
            best_f1 = current_f1
            best_epoch = epoch + 1
            patience = 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            patience += 1

        if patience >= args.patience:
            print("\nEarly stopping\n")
            break

    model.load_state_dict(best_state)
    return model, best_f1, best_epoch


# =========================================================
# ETAPAS
# =========================================================

def run_cv(args, df, tokenizer, device, out_dir):
    started_at = time.perf_counter()
    splits = make_splits(df, args.n_folds, args.seed)

    keys = ("sent_probs", "sent_true", "label_probs", "label_true")
    parts = {k: [] for k in keys}
    best_fold_f1 = -1.0
    best_checkpoint_path = out_dir / "best_fold_model.pt"

    for fold, (train_idx, val_idx) in enumerate(splits, start=1):
        train_df = df.iloc[train_idx].reset_index(drop=True)
        val_df = df.iloc[val_idx].reset_index(drop=True)

        describe(train_df, f"fold {fold} train")
        describe(val_df, f"fold {fold} test")

        train_loader = make_loader(train_df, tokenizer, args.max_len, args.batch_size, shuffle=True)
        val_loader = make_loader(val_df, tokenizer, args.max_len, args.batch_size, shuffle=False)

        model = MultiTaskBETO(args.model_name).to(device)
        model, fold_f1, best_epoch = train_one_fold(
            model, train_loader, val_loader, train_df, device, args
        )

        if fold_f1 > best_fold_f1:
            best_fold_f1 = fold_f1
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "best_fold": fold,
                    "best_epoch": best_epoch,
                    "best_f1": best_fold_f1,
                },
                best_checkpoint_path,
            )

        pred = predict(model, val_loader, device)
        for k in keys:
            parts[k].append(pred[k])

        del model
        gc.collect()
        torch.cuda.empty_cache()

    oof = {
        "sent_probs": np.vstack(parts["sent_probs"]),
        "sent_true": np.concatenate(parts["sent_true"]),
        "label_probs": np.vstack(parts["label_probs"]),
        "label_true": np.vstack(parts["label_true"]),
    }

    print("\nBuscando thresholds óptimos...")
    thresholds = find_best_thresholds(oof["label_true"], oof["label_probs"])
    print(json.dumps(thresholds, indent=2, ensure_ascii=False))

    metrics, _, _ = evaluate_predictions(oof, thresholds)
    print("\n=== RESULTADOS OOF ===")
    print(metrics.pivot(index="task", columns="average", values="f1"))

    with open(out_dir / "best_thresholds.json", "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2, ensure_ascii=False)

    results = {
        "model_label": args.model_label,
        "model_name": args.model_name,
        "data_path": str(Path(args.data).resolve()),
        "seed": args.seed,
        "n_folds": args.n_folds,
        "max_len": args.max_len,
        "cv_seconds": time.perf_counter() - started_at,
        "metrics": [
            {
                "task": row.task,
                "average": row.average,
                "precision": float(row.precision),
                "recall": float(row.recall),
                "f1": float(row.f1),
            }
            for row in metrics.itertuples(index=False)
        ],
    }
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return thresholds


def run_final(args, df, tokenizer, device, out_dir, thresholds):
    checkpoint_path = out_dir / "best_fold_model.pt"
    if not checkpoint_path.exists():
        raise SystemExit(
            f"No existe {checkpoint_path}. Ejecuta primero: python train.py --stage cv"
        )
    checkpoint = torch.load(checkpoint_path, map_location=device)
    model = MultiTaskBETO(args.model_name).to(device)
    model.load_state_dict(checkpoint["model_state"])

    model_path = out_dir / args.model_file
    torch.save(
        {
            "model_state": model.state_dict(),
            "thresholds": thresholds,
            "label_cols": LABEL_COLS,
            "sent_map": SENT2ID,
            "model_name": args.model_name,  # usados por infer.py
            "max_len": args.max_len,
            "best_fold": checkpoint["best_fold"],
            "best_epoch": checkpoint["best_epoch"],
            "best_f1": checkpoint["best_f1"],
        },
        model_path,
    )

    print(f"\nModelo guardado en:\n{model_path}")


def main(
    default_model=DEFAULT_MODEL,
    default_out_dir=T_DIR / "models_beto",
    default_model_file=DEFAULT_MODEL_FILE,
    default_model_label="BETO",
):
    args = parse_args(
        default_model,
        default_out_dir,
        default_model_file,
        default_model_label,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Modelo: {args.model_name}")

    df = load_data(args.data, args.text_col)
    describe(df, "dataset completo")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    thresholds = None

    if args.stage in ("cv", "all"):
        thresholds = run_cv(args, df, tokenizer, device, out_dir)

    if args.stage in ("final", "all"):
        if thresholds is None:
            thr_path = out_dir / "best_thresholds.json"
            if not thr_path.exists():
                raise SystemExit(f"No existe {thr_path}. Ejecuta primero: python train.py --stage cv")
            with open(thr_path, encoding="utf-8") as f:
                thresholds = json.load(f)

        run_final(args, df, tokenizer, device, out_dir, thresholds)


if __name__ == "__main__":
    main()
