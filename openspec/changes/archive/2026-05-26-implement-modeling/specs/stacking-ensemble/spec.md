## ADDED Requirements

### Requirement: Out-Of-Fold Predictions
The system SHALL generate Out-Of-Fold (OOF) predictions from base models (LightGBM and LSTM) to train the meta-learner.

#### Scenario: Prevent overfitting in Stacking
- **WHEN** training the Logistic Regression meta-learner in `train_stacking.py`
- **THEN** the system uses OOF predictions from base models rather than in-sample predictions.

### Requirement: Model Ensemble
The system SHALL combine tabular probability (P1) and sequence probability (P2) using Logistic Regression.

#### Scenario: Final Probability Generation
- **WHEN** the user executes the stacking ensemble step
- **THEN** the final classification probability is outputted and evaluated against actual test labels.
