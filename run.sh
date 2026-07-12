#!/bin/bash

set -euo pipefail

# 项目名
name="bilibili-signin"
# 打包镜像名
img_name="bilibili-signin"
# 配置文件映射路径
config_path="/opt/docker/bilibili-signin/config/"
# 日志文件映射路径
log_path="/opt/docker/bilibili-signin/logs/"

echo "----------开始构建项目----------"

if docker ps -aq -f "name=^${name}$" | grep -q .; then
  echo "----------存在历史项目----------"
  echo "----------开始删除----------"
  docker rm -f "${name}"
  echo "----------删除结束----------"
fi

docker build -t "${img_name}" .

echo "----------开始启动项目----------"

docker run --name "${name}" -d -v "${config_path}:/app/config" -v "${log_path}:/app/logs" "${img_name}"
docker ps
docker logs --tail=100 "${name}"

echo "----------启动项目完成----------"
