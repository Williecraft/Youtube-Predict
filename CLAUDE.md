# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Data Mining course final project (資料探勘導論, Spring 2026) predicting YouTube video virality. Two tasks:
1. **Classification:** Predict `is_viral_48h` (binary) using the first 0–3h of data after publish
2. **Regression:** Predict `log_next_24h_views` using the first 0–48h of data after publish

Full implementation specification is in `PROJECT_CONTEXT.md` (authoritative). `Proposal/Proposal.md` and `README.md` have additional context. No code has been written yet.

## Planned Directory Layout

```
src/
  crawler/          # Data collection scripts
  preprocessing/    # Cleaning, labeling, feature engineering, dataset splitting
  modeling/         # Model training and evaluation scripts
  utils/            # I/O, time conversion, logging helpers
data/
  raw/
    static/         # videos_static.json
    timeseries/     # video_stats_all.csv
    comments/by_video/{video_id}.jsonl
  processed/
    label_dataset.csv
    tabular_features.csv
    sequences_3h/{video_id}.npy
    sequences_48h/{sample_id}.npy
    regression_features_48h.csv
results/
  metrics.csv
  regression_metrics.csv
  feature_importance_shap.csv
  experiment_summary.csv
```

## Planned Stack

- **Scraping:** Selenium or urllib3 (HTTP 200 vs 303 for Shorts detection)
- **Data:** pandas, numpy
- **Models:** scikit-learn (Logistic Regression, stacking meta-learner), LightGBM, PyTorch or TensorFlow (LSTM)
- **Sentiment:** HuggingFace Transformers — `uer/roberta-base-finetuned-jd-binary-chinese`
- **Explainability:** SHAP

## Label Definition

```
effective_subscriber_count = max(subscriber_at_publish, 1000)
viral_view_threshold_48h   = max(min_abs_views, 2 * effective_subscriber_count)
is_viral_48h               = (views_48h >= viral_view_threshold_48h)
```

`views_48h` is measured at publish_time + 48 h. The `min_abs_views` constant is defined in PROJECT_CONTEXT.md Section 4.

## Feature Groups (Ablation Study)

| Group | Contents |
|-------|----------|
| A | Basic metadata + channel subscriber count |
| B | A + early traffic (0–3 h growth rate, engagement rate, views/min) |
| C1 | B + binary sentiment score |
| C2 | B + Valence-Arousal features |
| C3 | B + both sentiment feature sets |

12 tabular features total for LightGBM; see PROJECT_CONTEXT.md Section 6 for the exact list.

## LSTM Sequence Format

- **Classification:** T × 3 array `[view_count, like_count, comment_count]` over 0–3 h at 5–10 min intervals (T ≈ 18–36). Normalize each dimension by its max within that video's window.
- **Regression:** Same shape but over the 0–48 h window; the target is 48–72 h new views.

## Data Splitting Rules

Always split **by publish_time** (temporal, not random):
- Train: earliest 70 % of videos
- Valid: middle 15 %
- Test: latest 15 %

A single `video_id` must never appear in more than one split. Regression samples follow the same `video_id` split.

## Data Leakage Rules (Non-Negotiable)

1. Classification features use only 0–3 h data; `is_viral_48h` is derived solely from 48 h checkpoint.
2. Regression features use only 0–48 h data; the 48–72 h window contributes only the label.
3. Comments for classification features: only those crawled within 0–3 h of publish.
4. Scalers/encoders: fit on train set only.
5. Stacking meta-learner: trained on OOF (out-of-fold) predictions, never on in-sample train predictions.

## Stacking Architecture

```
LightGBM(tabular) → P1
LSTM(sequence)    → P2
LogisticRegression([P1, P2]) → final probability
```

## Shorts Detection

Use the HTTP redirect behavior: a `/shorts/{id}` URL that returns 200 is a Shorts video; 303 redirect indicates a regular video. This determines `is_shorts` feature and can be used to filter or stratify.

## Evaluation Metrics

- **Classification:** F1, AUC-ROC, Precision, Recall, PR-AUC
- **Regression:** MAE, RMSE, RMSLE, R²
