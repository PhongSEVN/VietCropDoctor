environment = "prod"
region      = "ap-southeast-1"

# EKS — production sizing with GPU node for vision-ai
cpu_node_count    = 2
cpu_instance_type = "t3.medium"
gpu_node_count    = 1
gpu_instance_type = "g4dn.xlarge"

# RDS — medium instance, multi-AZ enabled, deletion protection on
rds_instance_class  = "db.t3.medium"
db_username         = "vcdadmin"
# db_password: export TF_VAR_db_password=<secret>

# Redis
redis_node_type = "cache.t3.small"

# MSK
kafka_broker_instance_type = "kafka.t3.small"
# msk_password: export TF_VAR_msk_password=<secret>

# Kafka topics
kafka_topics = ["disease.detected", "chat.requested", "retrain.requested"]
