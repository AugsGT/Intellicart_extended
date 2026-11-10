#!/usr/bin/env bash
# Starts Redis and RabbitMQ for local development inside WSL, from a user-space micromamba
# environment (no root, no Docker). One-time install:
#   mkdir -p ~/mm && cd ~/mm
#   curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest -o mm.tar.bz2
#   python3 -c "import tarfile;tarfile.open('mm.tar.bz2').extract('bin/micromamba')"
#   MAMBA_ROOT_PREFIX=~/mm/root ~/mm/bin/micromamba create -y -n brokers -c conda-forge redis-server rabbitmq-server
# Then run this script inside WSL. RabbitMQ listens on IPv6 loopback, so from Windows use
#   RABBITMQ_URL=amqp://guest:guest@[::1]:5672/   REDIS_URL=redis://127.0.0.1:6379/0
#   RABBITMQ_MANAGEMENT_URL=http://[::1]:15672 (user guest / password guest, local development only)
export PATH=~/mm/root/envs/brokers/bin:$PATH
mkdir -p ~/mm/logs ~/mm/data/redis ~/mm/data/rabbit
cd ~/mm/data/redis
nohup redis-server --port 6379 --dir ~/mm/data/redis > ~/mm/logs/redis.log 2>&1 &
export RABBITMQ_MNESIA_BASE=~/mm/data/rabbit RABBITMQ_LOG_BASE=~/mm/logs RABBITMQ_NODENAME=rabbit@localhost
rabbitmq-plugins enable --offline rabbitmq_management > ~/mm/logs/plugins.log 2>&1
nohup rabbitmq-server > ~/mm/logs/rabbit.log 2>&1 &
sleep 25
redis-cli ping
rabbitmqctl -n rabbit@localhost await_startup 2>&1 | tail -1
