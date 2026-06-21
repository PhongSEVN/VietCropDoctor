"""
Feature store client — online (Redis) and offline (Parquet) access.

Online store:  Redis — low-latency feature retrieval for inference
Offline store: Parquet on MinIO — batch feature retrieval for training
"""
from __future__ import annotations

import os

from feast import FeatureStore


_REPO_PATH = os.getenv("FEAST_REPO_PATH", "/opt/feast")


def get_store() -> FeatureStore:
    """Return a Feast FeatureStore pointed at the configured repo."""
    return FeatureStore(repo_path=_REPO_PATH)


def get_online_features(entity_rows: list[dict], feature_refs: list[str]) -> dict:
    """Retrieve low-latency features from Redis for inference."""
    store = get_store()
    response = store.get_online_features(features=feature_refs, entity_rows=entity_rows)
    return response.to_dict()


def get_offline_features(entity_df, feature_refs: list[str]):
    """Retrieve historical features from Parquet for training."""
    store = get_store()
    return store.get_historical_features(entity_df=entity_df, features=feature_refs).to_df()
