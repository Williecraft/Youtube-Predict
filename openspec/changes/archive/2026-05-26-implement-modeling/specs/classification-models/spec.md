## ADDED Requirements

### Requirement: Logistic Regression Baseline
The system SHALL train a Logistic Regression model on tabular features to predict `is_viral_48h`. Features MUST be restricted to those derived from the 0-3h window.

#### Scenario: Train LR Baseline
- **WHEN** the user runs `train_logistic.py`
- **THEN** the model is trained on the earliest 70% of videos and evaluated on Valid/Test splits.

### Requirement: LightGBM Classification
The system SHALL train a LightGBM model on tabular features to predict `is_viral_48h`.

#### Scenario: Train LightGBM
- **WHEN** the user runs `train_lightgbm.py`
- **THEN** LightGBM is trained and probability predictions are stored for Stacking.

### Requirement: LSTM Classification
The system SHALL train a 2-layer LSTM model using PyTorch or TensorFlow on 0-3h time-series sequences.

#### Scenario: Train LSTM sequence classifier
- **WHEN** the user runs `train_lstm.py`
- **THEN** the model predicts `is_viral_48h` using `sequences_3h/*.npy` data.
