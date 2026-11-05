#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BETO multitarea para dataset_migracion_venezolana_labeled.csv

Mejoras respecto al script anterior:

- BETO (bert-base-spanish-wwm-cased)
- Oversampling solo en train
- Sin pos_weight
- Early stopping
- Threshold óptimo por etiqueta
- Macro F1 como métrica principal
- OOF predictions
- Reentrenamiento final
"""

import argparse
import gc
import json
import math
import os
import random
import re

from collections import Counter

import numpy as np
import pandas as pd

import torch
import torch.nn as nn

from sklearn.metrics import (
    precision_recall_curve,
    classification_report,
    precision_recall_fscore_support,
    f1_score,
)

from torch.utils.data import (
    Dataset,
    DataLoader,
)

from tqdm.auto import tqdm

from transformers import (
    AutoTokenizer,
    AutoModel,
    get_linear_schedule_with_warmup,
)

LABEL_COLS = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    #"Integración_social",
    #"Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]


SENT_COL = "sentimiento"

SENT2ID = {
    "Negativo": 0,
    "Neutro": 1,
    "Positivo": 2,
}

ID2SENT = {
    v: k for k, v in SENT2ID.items()
}

SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DEFAULT_DATA = os.path.join(
    SCRIPT_DIR,
    "..",
    "data",
    "dataset_migracion_venezolana_labeled.csv",
)


def parse_args():

    p = argparse.ArgumentParser()

    p.add_argument(
        "--data",
        default=DEFAULT_DATA
    )

    p.add_argument(
        "--text_col",
        default="Cuerpo"
    )

    p.add_argument(
        "--out_dir",
        default="models_beto"
    )

    p.add_argument(
        "--model_name",
        default="dccuchile/bert-base-spanish-wwm-cased"
    )

    p.add_argument(
        "--max_len",
        type=int,
        default=512
    )

    p.add_argument(
        "--n_folds",
        type=int,
        default=5
    )

    p.add_argument(
        "--epochs",
        type=int,
        default=32
    )

    p.add_argument(
        "--batch_size",
        type=int,
        default=2
    )

    p.add_argument(
        "--grad_accum",
        type=int,
        default=2
    )

    p.add_argument(
        "--lr",
        type=float,
        default=2e-5
    )

    p.add_argument(
        "--head_lr",
        type=float,
        default=1e-4
    )

    p.add_argument(
        "--warmup_ratio",
        type=float,
        default=0.1
    )

    p.add_argument(
        "--weight_decay",
        type=float,
        default=0.01
    )

    p.add_argument(
        "--label_loss_weight",
        type=float,
        default=1.5
    )

    p.add_argument(
        "--patience",
        type=int,
        default=4
    )

    p.add_argument(
        "--seed",
        type=int,
        default=42
    )

    p.add_argument(
        "--max_growth",
        type=float,
        default=3.0
    )

    return p.parse_args()


def set_seed(seed):

    random.seed(seed)

    np.random.seed(seed)

    torch.manual_seed(seed)

    torch.cuda.manual_seed_all(seed)


def clean_text(text):

    text = str(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()

def head_tail(
    text,
    head=1500,
    tail=1500
):
    text = str(text)

    if len(text) <= head + tail:
        return text

    return (
        text[:head]
        + "\n\n"
        + text[-tail:]
    )
def load_data(args):

    df = pd.read_csv(
        args.data,
        encoding="utf-8-sig"
    )

    cols = (
        [args.text_col]
        + [SENT_COL]
        + LABEL_COLS
    )

    missing = [
        c for c in cols
        if c not in df.columns
    ]

    if len(missing):

        raise ValueError(
            f"Faltan columnas: {missing}"
        )

    df = df.dropna(
        subset=[
            args.text_col,
            SENT_COL
        ]
    ).copy()

    df[SENT_COL] = (
        df[SENT_COL]
        .astype(str)
        .str.strip()
        .str.capitalize()
    )

    df["sent_id"] = (
        df[SENT_COL]
        .map(SENT2ID)
        .astype(int)
    )

    df[LABEL_COLS] = (
        df[LABEL_COLS]
        .fillna(0)
        .astype(int)
    )

    df["text_prep"] = (
        df[args.text_col]
        .map(clean_text)
        .map(head_tail)
    )


    df = df[
        df["text_prep"].str.len() > 0
    ].reset_index(drop=True)

    return df


def describe(df, name):

    s = Counter(df[SENT_COL])

    l = (
        df[LABEL_COLS]
        .sum()
        .astype(int)
        .to_dict()
    )

    print(
        f"[{name}] "
        f"n={len(df)} | "
        f"sentimiento={dict(s)} | "
        f"labels={l}"
    )

# =========================================================
# DATASET
# =========================================================

class NewsDataset(Dataset):

    def __init__(
        self,
        df,
        tokenizer,
        max_len
    ):

        self.texts = (
            df["text_prep"]
            .tolist()
        )

        self.sent = (
            df["sent_id"]
            .values
        )

        self.labels = (
            df[LABEL_COLS]
            .values
            .astype(np.float32)
        )

        self.tok = tokenizer

        self.max_len = max_len

    def __len__(self):

        return len(self.texts)

    def __getitem__(self, idx):

        enc = self.tok(
            self.texts[idx],
            truncation=True,
            max_length=self.max_len,
            padding=False,
            return_tensors="pt",
        )

        return {
            "input_ids":
                enc["input_ids"][0],

            "attention_mask":
                enc["attention_mask"][0],

            "sent":
                torch.tensor(
                    self.sent[idx],
                    dtype=torch.long,
                ),

            "labels":
                torch.tensor(
                    self.labels[idx],
                    dtype=torch.float,
                ),
        }


def collate_fn(batch):

    max_len = max(
        len(x["input_ids"])
        for x in batch
    )

    ids = []
    masks = []

    sent = []
    labels = []

    for row in batch:

        pad = (
            max_len
            - len(row["input_ids"])
        )

        ids.append(
            torch.cat(
                [
                    row["input_ids"],
                    torch.zeros(
                        pad,
                        dtype=torch.long
                    )
                ]
            )
        )

        masks.append(
            torch.cat(
                [
                    row["attention_mask"],
                    torch.zeros(
                        pad,
                        dtype=torch.long
                    )
                ]
            )
        )

        sent.append(row["sent"])

        labels.append(row["labels"])

    return {
        "input_ids":
            torch.stack(ids),

        "attention_mask":
            torch.stack(masks),

        "sent":
            torch.stack(sent),

        "labels":
            torch.stack(labels)
    }


# =========================================================
# OVERSAMPLING
# =========================================================

def random_oversample_sentiment(
    train_df,
    max_growth=3.0,
    seed=42
):

    counts = (
        train_df[SENT_COL]
        .value_counts()
    )

    target = counts.max()

    pieces = []

    rng = np.random.default_rng(seed)

    for sentiment in counts.index:

        subset = (
            train_df[
                train_df[SENT_COL]
                == sentiment
            ]
        )

        cur = len(subset)

        desired = min(
            target,
            int(cur * max_growth)
        )

        if desired > cur:

            extra_idx = rng.choice(
                subset.index,
                desired - cur,
                replace=True,
            )

            subset = pd.concat(
                [
                    subset,
                    train_df.loc[extra_idx]
                ],
                axis=0
            )

        pieces.append(subset)

    out = pd.concat(
        pieces,
        axis=0
    )

    out = (
        out.sample(
            frac=1,
            random_state=seed
        )
        .reset_index(drop=True)
    )

    return out


# =========================================================
# MODELO
# =========================================================

class MultiTaskBETO(nn.Module):

    def __init__(
        self,
        model_name,
        n_sent=3,
        n_labels=len(LABEL_COLS),
        dropout=0.3,
    ):

        super().__init__()

        self.encoder = (
            AutoModel
            .from_pretrained(
                model_name
            )
        )

        hidden = (
            self.encoder
            .config
            .hidden_size
        )

        self.dropout = (
            nn.Dropout(dropout)
        )

        self.sent_head = nn.Sequential(
            nn.Linear(
                hidden,
                hidden,
            ),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(
                hidden,
                n_sent,
            )
        )

        self.label_head = nn.Sequential(
            nn.Linear(
                hidden,
                hidden,
            ),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(
                hidden,
                n_labels,
            )
        )

    def forward(
        self,
        input_ids,
        attention_mask,
    ):

        out = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        if hasattr(
            out,
            "pooler_output"
        ) and out.pooler_output is not None:

            pooled = out.pooler_output

        else:

            pooled = (
                out.last_hidden_state[
                    :, 0
                ]
            )

        pooled = self.dropout(
            pooled
        )

        sent_logits = (
            self.sent_head(
                pooled
            )
        )

        label_logits = (
            self.label_head(
                pooled
            )
        )

        return (
            sent_logits,
            label_logits
        )

# =========================================================
# EVALUATION
# =========================================================

@torch.no_grad()
def predict(
    model,
    loader,
    device,
):

    model.eval()

    s_logits = []
    l_logits = []

    s_true = []
    l_true = []

    for batch in loader:

        ids = (
            batch["input_ids"]
            .to(device)
        )

        mask = (
            batch["attention_mask"]
            .to(device)
        )

        sent = (
            batch["sent"]
            .to(device)
        )

        labels = (
            batch["labels"]
            .to(device)
        )

        s_logit, l_logit = model(
            ids,
            mask
        )

        s_logits.append(
            s_logit.cpu()
        )

        l_logits.append(
            l_logit.cpu()
        )

        s_true.append(
            sent.cpu()
        )

        l_true.append(
            labels.cpu()
        )

    return {
        "sent_probs":
            torch.softmax(
                torch.cat(s_logits),
                dim=-1
            ).numpy(),

        "label_probs":
            torch.sigmoid(
                torch.cat(l_logits)
            ).numpy(),

        "sent_true":
            torch.cat(s_true)
            .numpy(),

        "label_true":
            torch.cat(l_true)
            .numpy()
            .astype(int),
    }


# =========================================================
# THRESHOLDS ÓPTIMOS
# =========================================================


def find_best_thresholds(
    y_true,
    probs,
):
    thresholds = {}

    for j, col in enumerate(LABEL_COLS):

        precision, recall, thr = precision_recall_curve(
            y_true[:, j],
            probs[:, j]
        )

        f1 = (
            2 * precision * recall
            / (precision + recall + 1e-12)
        )

        best_idx = np.argmax(f1[:-1])

        thresholds[col] = float(
            thr[best_idx]
        )

    return thresholds   


def apply_thresholds(
    probs,
    thresholds,
):

    pred = np.zeros_like(
        probs,
        dtype=np.int32
    )

    for j, col in enumerate(
        LABEL_COLS
    ):

        pred[:, j] = (
            probs[:, j]
            >= thresholds[col]
        ).astype(int)

    return pred


# =========================================================
# METRICS
# =========================================================

def evaluate_predictions(
    pred,
    label_thresholds,
):

    sent_pred = (
        pred["sent_probs"]
        .argmax(1)
    )

    label_pred = apply_thresholds(
        pred["label_probs"],
        label_thresholds
    )

    rows = []

    for task, yt, yp in [

        (
            "sent",
            pred["sent_true"],
            sent_pred
        ),

        (
            "label",
            pred["label_true"],
            label_pred
        ),
    ]:

        for avg in (
            "macro",
            "micro"
        ):

            p, r, f, _ = (
                precision_recall_fscore_support(
                    yt,
                    yp,
                    average=avg,
                    zero_division=0,
                )
            )

            rows.append(
                [
                    task,
                    avg,
                    p,
                    r,
                    f,
                ]
            )

    return (
        pd.DataFrame(
            rows,
            columns=[
                "task",
                "average",
                "precision",
                "recall",
                "f1",
            ]
        ),
        sent_pred,
        label_pred,
    )




# =========================================================
# TRAIN
# =========================================================

def train_one_fold(

    model,
    train_loader,
    val_loader,
    device,
    args,
):

    ce = nn.CrossEntropyLoss()

    bce = nn.BCEWithLogitsLoss()

    enc_params = []
    head_params = []

    for name, p in (
        model.named_parameters()
    ):

        if "encoder" in name:

            enc_params.append(p)

        else:

            head_params.append(p)

    optimizer = torch.optim.AdamW(

        [
            {
                "params":
                    enc_params,

                "lr":
                    args.lr,
            },
            {
                "params":
                    head_params,

                "lr":
                    args.head_lr,
            },
        ],

        weight_decay=
        args.weight_decay,
    )

    total_steps = (
        len(train_loader)
        * args.epochs
    )

    scheduler = (
        get_linear_schedule_with_warmup(

            optimizer,

            num_warmup_steps=
            int(
                total_steps
                *
                args.warmup_ratio
            ),

            num_training_steps=
            total_steps,
        )
    )

    scaler = (
        torch.cuda.amp.GradScaler(
            enabled=
            torch.cuda.is_available()
        )
    )

    best_f1 = -1

    patience = 0

    best_state = None

    for epoch in range(
        args.epochs
    ):

        model.train()

        losses = []

        pbar = tqdm(
            train_loader,
            leave=False
        )

        optimizer.zero_grad()

        for step, batch in enumerate(
            pbar
        ):

            ids = (
                batch["input_ids"]
                .to(device)
            )

            mask = (
                batch["attention_mask"]
                .to(device)
            )

            sent = (
                batch["sent"]
                .to(device)
            )

            labels = (
                batch["labels"]
                .to(device)
            )

            with torch.cuda.amp.autocast(

                enabled=
                torch.cuda.is_available()

            ):

                sent_logits, label_logits = (
                    model(
                        ids,
                        mask
                    )
                )

                loss_sent = ce(
                    sent_logits,
                    sent
                )

                loss_label = bce(
                    label_logits,
                    labels
                )

                loss = (
                    loss_sent
                    +
                    args.label_loss_weight
                    *
                    loss_label
                )

            scaler.scale(
                loss
            ).backward()

            if (
                (step + 1)
                %
                args.grad_accum
                == 0
            ):

                scaler.unscale_(
                    optimizer
                )

                torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    1.0
                )

                scaler.step(
                    optimizer
                )

                scaler.update()

                scheduler.step()

                optimizer.zero_grad()

            losses.append(
                loss.item()
            )

        print(
            f"epoch {epoch+1}/{args.epochs}"
            f" | train_loss="
            f"{np.mean(losses):.4f}"
        )

        val_pred = predict(
            model,
            val_loader,
            device,
        )

        thrs = find_best_thresholds(
            val_pred["label_true"],
            val_pred["label_probs"],
        )

        metrics, _, _ = (
            evaluate_predictions(
                val_pred,
                thrs,
            )
        )

        current_f1 = float(
            metrics[
                (
                    metrics.task
                    == "label"
                )
                &
                (
                    metrics.average
                    == "macro"
                )
            ]["f1"].iloc[0]
        )

        if current_f1 > best_f1:

            best_f1 = current_f1

            patience = 0

            best_state = {
                k: v.cpu().clone()
                for k, v in (
                    model
                    .state_dict()
                    .items()
                )
            }

        else:

            patience += 1

        if patience >= args.patience:

            print(
                "\nEarly stopping\n"
            )

            break

    model.load_state_dict(
        best_state
    )

    return model

# =========================================================
# CV
# =========================================================

def build_multilabel_target(df):

    sent_part = (
        pd.get_dummies(
            df[SENT_COL]
        )
        .values
    )

    label_part = (
        df[LABEL_COLS]
        .values
    )

    return np.hstack(
        [
            sent_part,
            label_part,
        ]
    )


def main():

    args = parse_args()

    os.makedirs(
        args.out_dir,
        exist_ok=True
    )

    set_seed(
        args.seed
    )

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print(
        f"Device: {device}"
    )

    print(
        f"Modelo: {args.model_name}"
    )

    df = load_data(args)

    describe(
        df,
        "dataset completo"
    )

    tokenizer = (
        AutoTokenizer
        .from_pretrained(
            args.model_name
        )
    )

    try:

        from iterstrat.ml_stratifiers import (
            MultilabelStratifiedKFold
        )

        X = np.zeros(
            len(df)
        )

        Y = (
            build_multilabel_target(
                df
            )
        )

        splitter = (
            MultilabelStratifiedKFold(
                n_splits=
                args.n_folds,
                shuffle=True,
                random_state=
                args.seed,
            )
        )

        splits = list(
            splitter.split(
                X,
                Y
            )
        )

    except ImportError:

        from sklearn.model_selection import (
            StratifiedKFold
        )

        splits = list(

            StratifiedKFold(
                n_splits=
                args.n_folds,
                shuffle=True,
                random_state=
                args.seed,
            ).split(
                df,
                df["sent_id"]
            )
        )

    oof_sent_probs = []

    oof_sent_true = []

    oof_label_probs = []

    oof_label_true = []

    

    for fold, (
        train_idx,
        val_idx
    ) in enumerate(
        splits,
        start=1
    ):

        train_df = (
            df.iloc[train_idx]
            .reset_index(
                drop=True
            )
        )


        val_df = (
            df.iloc[val_idx]
            .reset_index(
                drop=True
            )
        )

        describe(
            train_df,
            f"fold {fold} train (antes de balancear)"
        )

        train_df = (
            random_oversample_sentiment(
                train_df,
                max_growth=
                args.max_growth,
                seed=
                args.seed,
            )
        )

        describe(
            train_df,
            f"fold {fold} train (balanceado)"
        )

        describe(
            val_df,
            f"fold {fold} test"
        )

        train_ds = NewsDataset(
            train_df,
            tokenizer,
            args.max_len
        )

        val_ds = NewsDataset(
            val_df,
            tokenizer,
            args.max_len
        )

        train_loader = (
            DataLoader(
                train_ds,
                batch_size=
                args.batch_size,
                shuffle=True,
                collate_fn=
                collate_fn,
                pin_memory=True,
            )
        )

        val_loader = (
            DataLoader(
                val_ds,
                batch_size=
                args.batch_size,
                shuffle=False,
                collate_fn=
                collate_fn,
                pin_memory=True,
            )
        )

        model = (
            MultiTaskBETO(
                args.model_name
            )
            .to(device)
        )

        model = train_one_fold(
            model,
            train_loader,
            val_loader,
            device,
            args,
        )

        pred = predict(
            model,
            val_loader,
            device,
        )

        oof_sent_probs.append(
            pred["sent_probs"]
        )

        oof_sent_true.append(
            pred["sent_true"]
        )

        oof_label_probs.append(
            pred["label_probs"]
        )

        oof_label_true.append(
            pred["label_true"]
        )

        del model

        gc.collect()

        torch.cuda.empty_cache()

    oof = {

        "sent_probs":
            np.vstack(
                oof_sent_probs
            ),

        "sent_true":
            np.concatenate(
                oof_sent_true
            ),

        "label_probs":
            np.vstack(
                oof_label_probs
            ),

        "label_true":
            np.vstack(
                oof_label_true
            ),
    }

    print(
        "\nBuscando thresholds óptimos..."
    )

    label_thresholds = (
        find_best_thresholds(
            oof["label_true"],
            oof["label_probs"]
        )
    )

    


    print(
        json.dumps(
            label_thresholds,
            indent=2,
            ensure_ascii=False
        )
    )

    metrics, _, _ = (
        evaluate_predictions(
            oof,
            label_thresholds
        )
    )

    print(
        "\n=== RESULTADOS OOF ==="
    )

    print(
        metrics.pivot(
            index="task",
            columns="average",
            values="f1"
        )
    )

    with open(
        os.path.join(
            args.out_dir,
            "best_thresholds.json"
        ),
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            label_thresholds,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        "\nEntrenando modelo final..."
    )

    final_df = (
        random_oversample_sentiment(
            df,
            max_growth=
            args.max_growth,
            seed=
            args.seed,
        )
    )

    final_ds = NewsDataset(
        final_df,
        tokenizer,
        args.max_len
    )

    final_loader = DataLoader(
        final_ds,
        batch_size=
        args.batch_size,
        shuffle=True,
        collate_fn=
        collate_fn,
        pin_memory=True,
    )

    final_model = (
        MultiTaskBETO(
            args.model_name
        )
        .to(device)
    )

    ce = nn.CrossEntropyLoss()

    bce = (
        nn.BCEWithLogitsLoss()
    )

    optimizer = (
        torch.optim.AdamW(
            final_model.parameters(),
            lr=args.lr,
            weight_decay=
            args.weight_decay,
        )
    )

    for epoch in range(
        args.epochs
    ):

        final_model.train()

        losses = []

        for batch in final_loader:

            ids = (
                batch["input_ids"]
                .to(device)
            )

            mask = (
                batch["attention_mask"]
                .to(device)
            )

            sent = (
                batch["sent"]
                .to(device)
            )

            labels = (
                batch["labels"]
                .to(device)
            )

            optimizer.zero_grad()

            s_logit, l_logit = (
                final_model(
                    ids,
                    mask
                )
            )

            loss_s = ce(
                s_logit,
                sent
            )

            loss_l = bce(
                l_logit,
                labels
            )

            loss = (
                loss_s
                +
                args.label_loss_weight
                *
                loss_l
            )

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                final_model.parameters(),
                1.0
            )

            optimizer.step()

            losses.append(
                loss.item()
            )

        print(
            f"[FINAL] "
            f"epoch {epoch+1}/{args.epochs}"
            f" | loss="
            f"{np.mean(losses):.4f}"
        )

    model_path = os.path.join(
        args.out_dir,
        "beto_multitask.pt"
    )

    torch.save(
        {
            "model_state":
                final_model.state_dict(),

            "thresholds":
                label_thresholds,

            "label_cols":
                LABEL_COLS,

            "sent_map":
                SENT2ID,
        },
        model_path,
    )

    print(
        f"\nModelo guardado en:\n"
        f"{model_path}"
    )


if __name__ == "__main__":

    main()