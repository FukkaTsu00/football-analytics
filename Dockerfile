# Airflow image + our pipeline's libraries
FROM apache/airflow:2.10.5-python3.11

COPY requirements.txt /requirements.txt
# Pinning apache-airflow stops pip from upgrading Airflow's own dependencies
RUN pip install --no-cache-dir "apache-airflow==2.10.5" -r /requirements.txt