"""
Feast feature definitions for VietCropDoctor crop disease features.

Setup:
    pip install feast[redis]
    feast apply            # register features
    feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")

Usage:
    from feast import FeatureStore
    store = FeatureStore(repo_path="feature-store/")
    features = store.get_online_features(
        features=["disease_predictions:confidence", "disease_predictions:severity"],
        entity_rows=[{"image_id": "img_001"}],
    ).to_dict()
"""
from datetime import timedelta

from feast import Entity, Feature, FeatureView, FileSource, ValueType

# Entities

image_entity = Entity(
    name="image_id",
    value_type=ValueType.STRING,
    description="Unique identifier for a crop image submission",
)

session_entity = Entity(
    name="session_id",
    value_type=ValueType.STRING,
    description="User session for aggregating predictions",
)

# Data sources

prediction_source = FileSource(
    path="data/feature_store/predictions.parquet",
    timestamp_field="event_timestamp",
)

session_source = FileSource(
    path="data/feature_store/sessions.parquet",
    timestamp_field="event_timestamp",
)

# Feature views

disease_prediction_features = FeatureView(
    name="disease_predictions",
    entities=["image_id"],
    ttl=timedelta(days=7),
    features=[
        Feature(name="disease",           dtype=ValueType.STRING),
        Feature(name="confidence",        dtype=ValueType.FLOAT),
        Feature(name="severity",          dtype=ValueType.STRING),
        Feature(name="severity_score",    dtype=ValueType.FLOAT),
        Feature(name="uncertainty_score", dtype=ValueType.FLOAT),
        Feature(name="ensemble_used",     dtype=ValueType.BOOL),
        Feature(name="model_count",       dtype=ValueType.INT32),
        Feature(name="crop_type",         dtype=ValueType.STRING),
    ],
    online=True,
    source=prediction_source,
    tags={"team": "vision-ai", "project": "vietcropdoctor"},
)

session_aggregation_features = FeatureView(
    name="session_stats",
    entities=["session_id"],
    ttl=timedelta(hours=24),
    features=[
        Feature(name="prediction_count",       dtype=ValueType.INT32),
        Feature(name="avg_confidence",         dtype=ValueType.FLOAT),
        Feature(name="most_common_disease",    dtype=ValueType.STRING),
        Feature(name="outbreak_risk_score",    dtype=ValueType.FLOAT),
    ],
    online=True,
    source=session_source,
    tags={"team": "analytics", "project": "vietcropdoctor"},
)
