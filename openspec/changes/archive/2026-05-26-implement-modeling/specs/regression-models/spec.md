## ADDED Requirements

### Requirement: Regression Data Leakage Prevention
The regression models SHALL only use features derived from the 0-48h window to predict the 48h-72h view growth (`log_next_24h_views`). The 48h-72h view count MUST NOT be used as an input feature.

#### Scenario: Prevent data leakage in regression
- **WHEN** training regression models on `regression_features_48h.csv`
- **THEN** the target `next_24h_views` or `views_72h` is only used to compute the label, not as an input.

### Requirement: Regression Models Implementation
The system SHALL train at least a LightGBM Regressor and an LSTM Regressor on the 48h regression datasets.

#### Scenario: Train Regression
- **WHEN** the user runs `train_regression.py`
- **THEN** models are trained to predict `log_next_24h_views` and metrics are logged.
