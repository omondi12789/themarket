"""
Directional forecasting model.

Honest framing: this is a real, trainable gradient-boosted classifier over the
feature pipeline (app/features/pipeline.py) predicting next-bar direction
(up/down) with a calibrated probability — not a claim that any model can reliably
predict forex prices. Treat its output as one input to the AI decision system
(weighed alongside quant signals and risk checks), never as a standalone trade
trigger. Every prediction this produces is logged with the feature values and
model version that produced it (see Prediction storage in app/main.py), so
accuracy can be audited against what actually happened.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

from app.features.pipeline import build_feature_matrix


@dataclass
class TrainingReport:
    n_train_samples: int
    n_features: int
    cv_accuracy_mean: float
    cv_accuracy_std: float
    feature_importances: dict[str, float]


class DirectionalForecaster:
    """
    Binary classifier ensemble: P(next bar's close > this bar's close), blended
    from LightGBM and XGBoost — two different gradient-boosting implementations
    with different regularization/split-finding heuristics, so their errors are
    only partially correlated. Averaging their probabilities is a real, if modest,
    variance-reduction technique (not just "two models sounds better") — it's the
    same logic as a random forest's bagging, one level up. Both are tabular
    gradient-boosted trees rather than a deep model deliberately: on a few thousand
    rows of technical/statistical features, trees consistently outperform deep nets
    and retrain in seconds, cheap enough to do daily per symbol.
    """

    def __init__(self, lgbm_params: dict | None = None, xgb_params: dict | None = None):
        default_lgbm = dict(
            n_estimators=200, max_depth=4, learning_rate=0.03, subsample=0.8,
            colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=-1,
        )
        default_xgb = dict(
            n_estimators=200, max_depth=4, learning_rate=0.03, subsample=0.8,
            colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1, random_state=42,
            eval_metric="logloss", verbosity=0,
        )
        default_lgbm.update(lgbm_params or {})
        default_xgb.update(xgb_params or {})

        self.lgbm_model = LGBMClassifier(**default_lgbm)
        self.xgb_model = XGBClassifier(**default_xgb)
        self._feature_columns: list[str] = []
        self._fitted = False

    @staticmethod
    def _build_labels(df: pd.DataFrame) -> pd.Series:
        """1 if next bar closes higher than this bar, else 0."""
        return (df["close"].shift(-1) > df["close"]).astype(int)

    def train(self, df: pd.DataFrame, n_cv_splits: int = 5) -> TrainingReport:
        features = build_feature_matrix(df)
        labels = self._build_labels(df).reindex(features.index)

        valid = labels.notna()
        features, labels = features[valid], labels[valid].astype(int)

        if len(features) < 100:
            raise ValueError(
                f"only {len(features)} labeled samples after feature warmup — need at "
                "least 100 for a minimally meaningful train/validate split"
            )

        self._feature_columns = list(features.columns)

        # TimeSeriesSplit, not a random shuffle-split: this is the only CV strategy
        # that doesn't leak future information into training folds for time series.
        # Evaluated on the *blended* (ensemble) prediction each fold, not each model
        # separately, since the blend is what actually gets served in production.
        tscv = TimeSeriesSplit(n_splits=n_cv_splits)
        fold_accuracies = []
        for train_idx, test_idx in tscv.split(features):
            fold_lgbm = LGBMClassifier(**self.lgbm_model.get_params())
            fold_xgb = XGBClassifier(**self.xgb_model.get_params())
            fold_lgbm.fit(features.iloc[train_idx], labels.iloc[train_idx])
            fold_xgb.fit(features.iloc[train_idx], labels.iloc[train_idx])

            proba_lgbm = fold_lgbm.predict_proba(features.iloc[test_idx])[:, 1]
            proba_xgb = fold_xgb.predict_proba(features.iloc[test_idx])[:, 1]
            blended_proba = (proba_lgbm + proba_xgb) / 2
            preds = (blended_proba > 0.5).astype(int)
            fold_accuracies.append(float(np.mean(preds == labels.iloc[test_idx].values)))

        # Final models fit on all available data, for actual production inference.
        self.lgbm_model.fit(features, labels)
        self.xgb_model.fit(features, labels)
        self._fitted = True

        # Average the two models' feature importances (each normalized to sum to 1
        # first, since LightGBM and XGBoost report importances on different raw scales).
        lgbm_imp = self.lgbm_model.feature_importances_.astype(float)
        lgbm_imp = lgbm_imp / lgbm_imp.sum() if lgbm_imp.sum() > 0 else lgbm_imp
        xgb_imp = self.xgb_model.feature_importances_.astype(float)
        xgb_imp = xgb_imp / xgb_imp.sum() if xgb_imp.sum() > 0 else xgb_imp
        blended_importance = (lgbm_imp + xgb_imp) / 2
        importances = dict(zip(self._feature_columns, blended_importance))

        return TrainingReport(
            n_train_samples=len(features),
            n_features=len(self._feature_columns),
            cv_accuracy_mean=float(np.mean(fold_accuracies)),
            cv_accuracy_std=float(np.std(fold_accuracies)),
            feature_importances=dict(sorted(importances.items(), key=lambda kv: -kv[1])[:15]),
        )

    def predict_latest(self, df: pd.DataFrame) -> dict:
        if not self._fitted:
            raise RuntimeError("call train() before predict_latest()")

        features = build_feature_matrix(df)
        if features.empty:
            raise ValueError("not enough bars to compute features (need warmup period)")

        latest_row = features.iloc[[-1]][self._feature_columns]
        proba_lgbm = float(self.lgbm_model.predict_proba(latest_row)[0][1])
        proba_xgb = float(self.xgb_model.predict_proba(latest_row)[0][1])
        proba_up = (proba_lgbm + proba_xgb) / 2

        return {
            "direction": "up" if proba_up > 0.5 else "down",
            "probability_up": proba_up,
            "confidence": abs(proba_up - 0.5) * 2,  # 0 at coin-flip, 1 at full certainty
            "as_of": features.index[-1].isoformat(),
            "feature_snapshot": {k: float(v) for k, v in latest_row.iloc[0].to_dict().items()},
            "model_breakdown": {"lightgbm_probability_up": proba_lgbm, "xgboost_probability_up": proba_xgb},
        }
