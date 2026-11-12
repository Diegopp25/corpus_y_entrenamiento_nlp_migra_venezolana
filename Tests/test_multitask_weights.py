import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parents[1] / "modelling" / "T-01_beto_multitask"
sys.path.insert(0, str(MODEL_DIR))

from modelling.beto.preprocess import LABEL_COLS, compute_loss_weights


def test_compute_loss_weights_balances_sentiment_and_multilabels():
    data = {"sent_id": [0, 0, 0, 1, 2]}
    label_values = [
        [1, 0, 0, 0, 0],
        [1, 1, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1],
    ]
    data.update(
        {
            column: values
            for column, values in zip(LABEL_COLS, label_values)
        }
    )

    sentiment_weights, label_pos_weights = compute_loss_weights(pd.DataFrame(data))

    np.testing.assert_allclose(sentiment_weights, [5 / 9, 5 / 3, 5 / 3])
    np.testing.assert_allclose(label_pos_weights, [4.0, 1.5, 1.0, 1.0, 1.0])


def test_compute_loss_weights_handles_missing_sentiment_class():
    data = {"sent_id": [0, 0, 2]}
    data.update({column: [0, 0, 0] for column in LABEL_COLS})

    sentiment_weights, label_pos_weights = compute_loss_weights(pd.DataFrame(data))

    np.testing.assert_allclose(sentiment_weights, [0.75, 0.0, 1.5])
    np.testing.assert_allclose(label_pos_weights, np.ones(len(LABEL_COLS)))
