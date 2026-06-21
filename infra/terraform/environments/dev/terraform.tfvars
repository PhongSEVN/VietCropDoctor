environment = "dev"
region      = "ap-southeast-1"

# EKS — smaller nodes, no GPU for dev
cpu_node_count    = 2
cpu_instance_type = "t3.micro"
gpu_node_count    = 0

# RDS — smallest instance, no multi-AZ, no deletion protection
rds_instance_class  = "db.t3.micro"
db_username         = "vcdadmin"
# db_password: export TF_VAR_db_password=<secret>

# Redis
redis_node_type = "cache.t3.micro"

# MSK
kafka_broker_instance_type = "kafka.t3.small"
# msk_password: export TF_VAR_msk_password=<secret>

# Kafka topics
kafka_topics = ["disease.detected", "chat.requested", "retrain.requested"]
