# train_cv.py
#
# Validación cruzada estratificada (5 folds, una o varias semillas) para el
# modelo multitarea (sentimiento + encuadres).
#
# Qué resuelve:
#   * Cada artículo se evalúa exactamente una vez como validación (156 en vez de 32).
#   * Los umbrales por encuadre se eligen SIN fuga: para evaluar el fold k se
#     ajustan con las predicciones out-of-fold de los otros folds.
#   * No se elige "el mejor epoch" por fold; se elige un único número de epochs
#     para todos mirando la curva promedio.
#   * Opcional: congelar las primeras N capas del encoder (FREEZE_LAYERS).
#   * Al final (TRAIN_FINAL=True) entrena con el 100% de los datos y guarda
#     model.pt + thresholds.json listos para la app.
#
# La configuración replica tu train_multitask.py (DistilBERT español).

import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader
from transformers import (
    AutoModel,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

# ==========================================================
# CONFIG
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

DATA_PATH = PROJECT_ROOT / "Data" / "dataset_preprocessed.csv"
MODEL_OUTPUT_DIR = BASE_DIR / "models" / "multitask_distilbert"
CV_RESULTS_PATH = BASE_DIR / f"cv_results_{MODEL_OUTPUT_DIR.name}.json"

ID_COLUMN = "ID"
SENTIMENT_COLUMN = "sentimiento"

# Cuerpo original + limpieza básica (URLs, emojis, espacios) de text_utils.py.
# Si pones APPLY_BASIC_CLEAN = False se usa el texto tal cual.
TEXT_COLUMN = "Cuerpo"
APPLY_BASIC_CLEAN = True

MULTILABEL_COLUMNS = [
    "Acceso_a_servicios",
    "Empleo_y_economía",
    "Integración_social",
    "Otros",
    "Politica_migratoria",
    "Seguridad",
    "Transito_migratorio",
]

MODEL_NAME = "dccuchile/distilbert-base-spanish-uncased"

# --- validación cruzada ---
RANDOM_STATE = 42
N_FOLDS = 5
SEEDS = [RANDOM_STATE]  # varias semillas: [42, 43, 44] (tarda 3 veces más)
TRAIN_FINAL = True      # entrenar con todos los datos al terminar la CV

# --- entrenamiento ---
MAX_LEN = 512
BATCH_SIZE = 4
EPOCHS = 15
WARMUP_RATIO = 0.10
MAX_GRAD_NORM = 1.0
WEIGHT_DECAY = 0.01

LR_ENCODER = 2e-5       # encoder preentrenado (opción: 1e-5 con más EPOCHS)
LR_HEADS = 1e-3           # cabezas lineales nuevas

# Congela embeddings + las primeras N capas del encoder.
# 0 = no congelar nada. OJO: DistilBERT tiene solo 6 capas; probar 2 o 3
# (con 6 congelas todo el encoder y solo entrenan las cabezas).
FREEZE_LAYERS = 0

CLASS_WEIGHT_POWER = 1.0
POS_WEIGHT_POWER = 0.5
POS_WEIGHT_MAX = 5.0

DEFAULT_THRESHOLD = 0.5
THRESHOLD_GRID = np.arange(0.20, 0.801, 0.05)
MIN_POS_FOR_TUNING = 8   # (tu script usa 5; aquí el ajuste usa ~125 artículos, no 32)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
USE_AMP = DEVICE == "cuda"

print(f"Usando dispositivo: {DEVICE} | AMP: {USE_AMP}")

# ==========================================================
# DATA
# ==========================================================

df = pd.read_csv(DATA_PATH)
df = df.dropna(subset=[TEXT_COLUMN])
df = df.drop_duplicates(subset=[ID_COLUMN]).reset_index(drop=True)

if APPLY_BASIC_CLEAN:
    sys.path.insert(0, str(BASE_DIR))
    from text_utils import basic_clean   # mismo limpiado que usará la app

    texts = [basic_clean(t) for t in df[TEXT_COLUMN]]
else:
    texts = [str(t) for t in df[TEXT_COLUMN]]

sentiment_classes = sorted(df[SENTIMENT_COLUMN].unique())
sentiment2id = {c: i for i, c in enumerate(sentiment_classes)}

y_sent = df[SENTIMENT_COLUMN].map(sentiment2id).values
y_multi = df[MULTILABEL_COLUMNS].values.astype(int)
N = len(df)

print(f"\nArtículos: {N}")
print(df[SENTIMENT_COLUMN].value_counts().to_string())
print("\nEncuadres:", dict(zip(MULTILABEL_COLUMNS, y_multi.sum(0).tolist())))

MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

# tokeniza una sola vez (sin padding; el padding es dinámico por batch)
encodings = tokenizer(texts, truncation=True, max_length=MAX_LEN)
input_ids_all = encodings["input_ids"]
attention_all = encodings["attention_mask"]

# ==========================================================
# DATASET / COLLATE
# ==========================================================

class IndexedDataset(torch.utils.data.Dataset):

    def __init__(self, indices):
        self.indices = list(indices)

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        j = self.indices[i]
        return {
            "input_ids": input_ids_all[j],
            "attention_mask": attention_all[j],
            "sentiment": int(y_sent[j]),
            "multilabel": y_multi[j].astype(np.float32),
        }


def collate(batch):
    padded = tokenizer.pad(
        {
            "input_ids": [b["input_ids"] for b in batch],
            "attention_mask": [b["attention_mask"] for b in batch],
        },
        padding=True,
        return_tensors="pt",
    )
    return {
        "input_ids": padded["input_ids"],
        "attention_mask": padded["attention_mask"],
        "sentiment": torch.tensor([b["sentiment"] for b in batch]),
        "multilabel": torch.tensor(np.stack([b["multilabel"] for b in batch])),
    }


# ==========================================================
# MODEL (idéntico al de la app)
# ==========================================================

class MultiTaskBERT(nn.Module):

    def __init__(self, model_name, num_sentiment_classes, num_labels):
        super().__init__()

        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size = self.encoder.config.hidden_size

        self.dropout = nn.Dropout(0.2)
        self.sentiment_head = nn.Linear(hidden_size, num_sentiment_classes)
        self.multilabel_head = nn.Linear(hidden_size, num_labels)

    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(
            input_ids=input_ids, attention_mask=attention_mask
        )
        cls_embedding = self.dropout(outputs.last_hidden_state[:, 0])

        return (
            self.sentiment_head(cls_embedding),
            self.multilabel_head(cls_embedding),
        )


def freeze_encoder_layers(model, n_layers):
    """Congela embeddings y las primeras n_layers capas del encoder."""
    if n_layers <= 0:
        return

    enc = model.encoder

    if hasattr(enc, "encoder") and hasattr(enc.encoder, "layer"):      # BERT/BETO
        layers = enc.encoder.layer
    elif hasattr(enc, "transformer") and hasattr(enc.transformer, "layer"):  # DistilBERT
        layers = enc.transformer.layer
    else:
        raise RuntimeError("No encontré las capas del encoder para congelar.")

    for p in enc.embeddings.parameters():
        p.requires_grad = False

    for layer in layers[:n_layers]:
        for p in layer.parameters():
            p.requires_grad = False

    print(f"  Congeladas: embeddings + {n_layers}/{len(layers)} capas")


# ==========================================================
# UMBRALES
# ==========================================================

def tune_thresholds(y_true, y_prob):
    """Umbral por encuadre que maximiza F1. Con pocos positivos queda en 0.5."""
    thresholds = np.full(y_true.shape[1], DEFAULT_THRESHOLD)

    for j in range(y_true.shape[1]):
        if y_true[:, j].sum() < MIN_POS_FOR_TUNING:
            continue

        best_f1, best_t = -1.0, DEFAULT_THRESHOLD

        for t in THRESHOLD_GRID:
            f1 = f1_score(
                y_true[:, j], (y_prob[:, j] >= t).astype(int), zero_division=0
            )
            better = f1 > best_f1 + 1e-9
            tie_closer = (
                abs(f1 - best_f1) <= 1e-9
                and abs(t - DEFAULT_THRESHOLD) < abs(best_t - DEFAULT_THRESHOLD)
            )
            if better or tie_closer:
                best_f1, best_t = f1, float(t)

        thresholds[j] = best_t

    return thresholds


# ==========================================================
# ENTRENAMIENTO DE UN MODELO
# ==========================================================

def train_model(train_idx, val_idx, seed, epochs, tag=""):
    """Entrena con train_idx. Si val_idx no es None, devuelve probabilidades
    de validación en CADA epoch: (sent [E,n,3], multi [E,n,7])."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    # pesos calculados solo con el train de este fold
    cw = compute_class_weight(
        "balanced",
        classes=np.arange(len(sentiment_classes)),
        y=y_sent[train_idx],
    ) ** CLASS_WEIGHT_POWER
    cw = cw / cw.mean()

    pos = y_multi[train_idx].sum(0).astype(float)
    neg = len(train_idx) - pos
    pw = np.clip(
        (neg / np.maximum(pos, 1)) ** POS_WEIGHT_POWER, 1.0, POS_WEIGHT_MAX
    )

    model = MultiTaskBERT(
        MODEL_NAME, len(sentiment_classes), len(MULTILABEL_COLUMNS)
    ).to(DEVICE)

    freeze_encoder_layers(model, FREEZE_LAYERS)

    sent_loss_fn = nn.CrossEntropyLoss(
        weight=torch.tensor(cw, dtype=torch.float).to(DEVICE)
    )
    multi_loss_fn = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor(pw, dtype=torch.float).to(DEVICE)
    )

    optimizer = torch.optim.AdamW(
        [
            {
                "params": [p for p in model.encoder.parameters() if p.requires_grad],
                "lr": LR_ENCODER,
            },
            {
                "params": list(model.sentiment_head.parameters())
                + list(model.multilabel_head.parameters()),
                "lr": LR_HEADS,
            },
        ],
        weight_decay=WEIGHT_DECAY,
    )

    train_loader = DataLoader(
        IndexedDataset(train_idx),
        batch_size=BATCH_SIZE,
        shuffle=True,
        collate_fn=collate,
    )
    val_loader = (
        DataLoader(
            IndexedDataset(val_idx),
            batch_size=BATCH_SIZE,
            shuffle=False,
            collate_fn=collate,
        )
        if val_idx is not None
        else None
    )

    total_steps = len(train_loader) * epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer, int(total_steps * WARMUP_RATIO), total_steps
    )
    scaler = torch.amp.GradScaler("cuda", enabled=USE_AMP)

    sent_hist, multi_hist = [], []

    for epoch in range(epochs):

        model.train()
        t0 = time.time()
        total_loss = 0.0

        for batch in train_loader:
            optimizer.zero_grad()

            ids = batch["input_ids"].to(DEVICE)
            mask = batch["attention_mask"].to(DEVICE)
            s = batch["sentiment"].to(DEVICE)
            m = batch["multilabel"].to(DEVICE)

            with torch.autocast(
                device_type="cuda", dtype=torch.float16, enabled=USE_AMP
            ):
                s_logits, m_logits = model(ids, mask)
                loss = sent_loss_fn(s_logits, s) + multi_loss_fn(m_logits, m)

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad],
                MAX_GRAD_NORM,
            )
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()

            total_loss += loss.item()

        msg = (
            f"  {tag} epoch {epoch + 1}/{epochs} "
            f"loss {total_loss / len(train_loader):.4f} "
            f"({time.time() - t0:.0f}s)"
        )

        if val_loader is not None:
            model.eval()
            sp, mp = [], []

            with torch.no_grad():
                for batch in val_loader:
                    with torch.autocast(
                        device_type="cuda",
                        dtype=torch.float16,
                        enabled=USE_AMP,
                    ):
                        s_logits, m_logits = model(
                            batch["input_ids"].to(DEVICE),
                            batch["attention_mask"].to(DEVICE),
                        )
                    sp.append(torch.softmax(s_logits.float(), -1).cpu().numpy())
                    mp.append(torch.sigmoid(m_logits.float()).cpu().numpy())

            sent_hist.append(np.concatenate(sp))
            multi_hist.append(np.concatenate(mp))

            f_s = f1_score(
                y_sent[val_idx], sent_hist[-1].argmax(1), average="macro"
            )
            f_m = f1_score(
                y_multi[val_idx],
                (multi_hist[-1] >= DEFAULT_THRESHOLD).astype(int),
                average="macro",
                zero_division=0,
            )
            msg += f" | sent F1 {f_s:.3f} | multi F1@0.5 {f_m:.3f}"

        print(msg)

    if val_loader is None:
        return model, None, None

    del model, optimizer
    if DEVICE == "cuda":
        torch.cuda.empty_cache()

    return None, np.stack(sent_hist), np.stack(multi_hist)


# ==========================================================
# VALIDACIÓN CRUZADA
# ==========================================================

all_seed_results = []
seed_thresholds = []

for seed in SEEDS:

    print("\n" + "#" * 70)
    print(f"# SEMILLA {seed} — {N_FOLDS} folds")
    print("#" * 70)

    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)

    oof_sent = np.zeros((EPOCHS, N, len(sentiment_classes)))
    oof_multi = np.zeros((EPOCHS, N, len(MULTILABEL_COLUMNS)))
    fold_of = np.zeros(N, dtype=int)

    for k, (tr_idx, va_idx) in enumerate(skf.split(np.zeros(N), y_sent)):
        print(f"\n--- Fold {k + 1}/{N_FOLDS} | train {len(tr_idx)} | val {len(va_idx)} ---")

        _, s_hist, m_hist = train_model(
            tr_idx, va_idx, seed=seed + k, epochs=EPOCHS, tag=f"[f{k + 1}]"
        )

        oof_sent[:, va_idx] = s_hist
        oof_multi[:, va_idx] = m_hist
        fold_of[va_idx] = k

    # ---- elegir un epoch común mirando la curva promedio por fold ----
    curve = np.zeros(EPOCHS)

    for e in range(EPOCHS):
        scores = []
        for k in range(N_FOLDS):
            m = fold_of == k
            f_s = f1_score(
                y_sent[m], oof_sent[e][m].argmax(1), average="macro"
            )
            f_m = f1_score(
                y_multi[m],
                (oof_multi[e][m] >= DEFAULT_THRESHOLD).astype(int),
                average="macro",
                zero_division=0,
            )
            scores.append((f_s + f_m) / 2)
        curve[e] = np.mean(scores)

    best_e = int(curve.argmax())

    print("\nCurva promedio por epoch ((sent F1 + multi F1@0.5)/2):")
    print("  " + " ".join(f"{e + 1}:{v:.3f}" for e, v in enumerate(curve)))
    print(f"Epoch elegido: {best_e + 1}")

    probs_s = oof_sent[best_e]
    probs_m = oof_multi[best_e]

    # ---- umbrales sin fuga: ajustados con los OTROS folds ----
    pred_s = probs_s.argmax(1)
    pred_m_fixed = (probs_m >= DEFAULT_THRESHOLD).astype(int)
    pred_m_tuned = np.zeros_like(pred_m_fixed)

    for k in range(N_FOLDS):
        m = fold_of == k
        thr_k = tune_thresholds(y_multi[~m], probs_m[~m])
        pred_m_tuned[m] = (probs_m[m] >= thr_k).astype(int)

    # umbrales finales: ajustados con todas las predicciones out-of-fold
    thr_final = tune_thresholds(y_multi, probs_m)
    seed_thresholds.append(thr_final)

    def per_fold(pred, y, avg_kwargs):
        return [
            f1_score(y[fold_of == k], pred[fold_of == k], **avg_kwargs)
            for k in range(N_FOLDS)
        ]

    sent_folds = per_fold(pred_s, y_sent, dict(average="macro"))
    multi_fixed_folds = per_fold(
        pred_m_fixed, y_multi, dict(average="macro", zero_division=0)
    )
    multi_tuned_folds = per_fold(
        pred_m_tuned, y_multi, dict(average="macro", zero_division=0)
    )

    result = {
        "seed": seed,
        "epoch": best_e + 1,
        "sent_macro_f1_pooled": f1_score(y_sent, pred_s, average="macro"),
        "sent_macro_f1_folds_mean": float(np.mean(sent_folds)),
        "sent_macro_f1_folds_std": float(np.std(sent_folds)),
        "multi_macro_f1_thr05_pooled": f1_score(
            y_multi, pred_m_fixed, average="macro", zero_division=0
        ),
        "multi_macro_f1_tuned_pooled": f1_score(
            y_multi, pred_m_tuned, average="macro", zero_division=0
        ),
        "multi_micro_f1_tuned_pooled": f1_score(
            y_multi, pred_m_tuned, average="micro", zero_division=0
        ),
        "multi_macro_f1_tuned_folds_mean": float(np.mean(multi_tuned_folds)),
        "multi_macro_f1_tuned_folds_std": float(np.std(multi_tuned_folds)),
    }
    all_seed_results.append(result)

    print("\n" + "=" * 70)
    print(f"RESULTADOS SEMILLA {seed} (cada artículo evaluado una vez)")
    print("=" * 70)
    print(
        f"Sentimiento  macro F1: {result['sent_macro_f1_pooled']:.4f}  "
        f"(folds: {result['sent_macro_f1_folds_mean']:.3f} ± {result['sent_macro_f1_folds_std']:.3f})"
    )
    print(
        f"Encuadres macro F1 umbral 0.5:      {result['multi_macro_f1_thr05_pooled']:.4f}"
    )
    print(
        f"Encuadres macro F1 umbral ajustado: {result['multi_macro_f1_tuned_pooled']:.4f}  "
        f"(folds: {result['multi_macro_f1_tuned_folds_mean']:.3f} ± {result['multi_macro_f1_tuned_folds_std']:.3f})"
        f" | micro: {result['multi_micro_f1_tuned_pooled']:.4f}"
    )
    print("\nSentimiento:")
    print(
        classification_report(
            y_sent, pred_s, target_names=sentiment_classes, zero_division=0
        )
    )
    print("Encuadres (umbral ajustado sin fuga):")
    print(
        classification_report(
            y_multi,
            pred_m_tuned,
            target_names=MULTILABEL_COLUMNS,
            zero_division=0,
        )
    )

# ==========================================================
# RESUMEN ENTRE SEMILLAS
# ==========================================================

print("\n" + "#" * 70)
print("RESUMEN")
print("#" * 70)

for key in [
    "sent_macro_f1_pooled",
    "multi_macro_f1_thr05_pooled",
    "multi_macro_f1_tuned_pooled",
]:
    vals = [r[key] for r in all_seed_results]
    print(f"{key}: {np.mean(vals):.4f} ± {np.std(vals):.4f}  (semillas: {len(vals)})")

final_epochs = int(round(np.mean([r["epoch"] for r in all_seed_results])))
final_thresholds = np.mean(seed_thresholds, axis=0)

thr_dict = {n: float(t) for n, t in zip(MULTILABEL_COLUMNS, final_thresholds)}
print("\nUmbrales finales:", {k: round(v, 2) for k, v in thr_dict.items()})
print("Epochs para el modelo final:", final_epochs)

with open(CV_RESULTS_PATH, "w", encoding="utf-8") as f:
    json.dump(
        {
            "config": {
                "text_column": TEXT_COLUMN,
                "max_len": MAX_LEN,
                "epochs": EPOCHS,
                "lr_encoder": LR_ENCODER,
                "lr_heads": LR_HEADS,
                "freeze_layers": FREEZE_LAYERS,
                "n_folds": N_FOLDS,
                "seeds": SEEDS,
            },
            "per_seed": all_seed_results,
            "thresholds": thr_dict,
            "final_epochs": final_epochs,
        },
        f,
        ensure_ascii=False,
        indent=2,
    )

print(f"Resultados guardados en {CV_RESULTS_PATH}")

# ==========================================================
# MODELO FINAL (100% de los datos)
# ==========================================================

if TRAIN_FINAL:
    print("\n" + "#" * 70)
    print(f"# MODELO FINAL con todos los datos ({final_epochs} epochs)")
    print("#" * 70)

    model, _, _ = train_model(
        np.arange(N), None, seed=SEEDS[0], epochs=final_epochs, tag="[final]"
    )

    with open(
        MODEL_OUTPUT_DIR / "sentiment_classes.json", "w", encoding="utf-8"
    ) as f:
        json.dump(sentiment_classes, f, ensure_ascii=False, indent=2)

    with open(
        MODEL_OUTPUT_DIR / "thresholds.json", "w", encoding="utf-8"
    ) as f:
        json.dump(thr_dict, f, ensure_ascii=False, indent=2)

    torch.save(model.state_dict(), MODEL_OUTPUT_DIR / "model.pt")
    tokenizer.save_pretrained(MODEL_OUTPUT_DIR)

    print("Modelo final guardado en", MODEL_OUTPUT_DIR)

print("\nListo.")