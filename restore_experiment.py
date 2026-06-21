"""Restore deleted MLflow experiment."""
import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
client = mlflow.tracking.MlflowClient()

# Find the deleted experiment
deleted = client.search_experiments(
    filter_string="name='plant-disease-classification'",
    view_type=mlflow.entities.ViewType.DELETED_ONLY,
)

if deleted:
    for exp in deleted:
        print(f"Restoring experiment: id={exp.experiment_id}, name={exp.name}")
        client.restore_experiment(exp.experiment_id)
    print("Done! Experiment restored.")
else:
    print("No deleted experiment found with that name.")
    print("Listing all experiments (including deleted):")
    all_exps = client.search_experiments(view_type=mlflow.entities.ViewType.ALL)
    for e in all_exps:
        print(f"  id={e.experiment_id}  name={e.name}  lifecycle={e.lifecycle_stage}")
