# basic image
FROM python:3.10-slim

# work dir
WORKDIR /app

# copy code
COPY app/ app/
COPY requirements.txt .

# install system dependencies
RUN apt-get update && apt-get install -y gcc \
    && rm -rf /var/lib/apt/lists/*

# install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# run script
CMD ["python", "app/run_script.py"]