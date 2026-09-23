# 基础镜像
FROM python:3.13.2-slim

# 工作目录
WORKDIR /app

# 先复制依赖文件，安装依赖（利用 Docker 缓存层）
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部代码
COPY . .

# 暴露端口
EXPOSE 8000
