FROM ghcr.io/mlflow/mlflow:v3.17.2
# The base image ships without the Postgres driver and S3 client this stack uses.
RUN pip install --no-cache-dir psycopg2-binary boto3
