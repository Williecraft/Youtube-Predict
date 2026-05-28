## ADDED Requirements

### Requirement: Classification Metrics Evaluation
The system SHALL compute F1, AUC-ROC, Precision, Recall, and PR-AUC for classification tasks.

#### Scenario: Evaluate Classification
- **WHEN** the evaluate step is run for a classifier
- **THEN** the results are appended to `results/metrics.csv`.

### Requirement: Regression Metrics Evaluation
The system SHALL compute MAE, RMSE, RMSLE, and R² for regression tasks.

#### Scenario: Evaluate Regression
- **WHEN** the evaluate step is run for a regressor
- **THEN** the results are appended to `results/regression_metrics.csv`.

### Requirement: SHAP Feature Importance
The system SHALL generate SHAP values for LightGBM tabular features to explain model decisions.

#### Scenario: Run SHAP Analysis
- **WHEN** the user runs `shap_analysis.py`
- **THEN** feature importance summaries are exported to `results/feature_importance_shap.csv`.
