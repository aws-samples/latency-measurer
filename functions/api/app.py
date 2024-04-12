import gzip
import json
import os
import random
from datetime import datetime

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from reachability import get_ipsets

app = APIGatewayRestResolver()
tracer = Tracer()
logger = Logger()

s3 = boto3.client("s3")


@app.get("/<ipset>")
@tracer.capture_method
def get(ipset):
    get_object = s3.get_object(
        Bucket=os.environ["BUCKET_NAME"], Key=os.environ["IPSETS_S3_KEY"]
    )
    ipsets = get_ipsets(json.loads(get_object["Body"].read().decode("utf-8")))
    if ipset in ipsets:
        return random.choice(ipsets[ipset]["ipset"])
    return None


@app.post("/<ipset>/<host>")
@tracer.capture_method
def post(ipset, host):
    now = datetime.utcnow()
    key = f"results/ipset={ipset}/host={host}/year={now.year}/month={now.month}/day={now.day}/hour={now.hour}/minute={now.minute}/results.json.gz"
    body = json.loads(app.current_event.body)
    data = gzip.compress(bytes(json.dumps(body), "utf-8"))
    s3.put_object(Bucket=os.environ["BUCKET_NAME"], Key=key, Body=data)
    return None


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    print(json.dumps(event))
    return app.resolve(event, context)
