import gzip
import json
import os
import re

import boto3
import yaml
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from reachability import get_lookups, get_params

tracer = Tracer()
logger = Logger()

s3 = boto3.client("s3")
ssm = boto3.client("ssm")


def get_document():
    with open("document.yaml", "r", encoding="utf-8") as f:
        document_txt = f.read()
    variables = set(re.findall(r"os\.environ\[\"([A-Z_0-9]+)\"\]", document_txt))
    for var in variables:
        document_txt = document_txt.replace(f'os.environ["{var}"]', os.environ[var])
    document_dict = yaml.safe_load(document_txt)
    script_txt = open("script.py", "r", encoding="utf-8").read()
    step_id, getips_step = next(
        (n, m)
        for n, m in enumerate(document_dict["mainSteps"])
        if m["name"] == "GetIps"
    )
    getips_step["inputs"]["Script"] = script_txt
    return step_id, document_dict


def put_lookups(bucket, lookups):
    s3.put_object(
        Bucket=bucket,
        Key="lookups/lookups.json.gz",
        Body=gzip.compress(bytes("\n".join([json.dumps(r) for r in lookups]), "utf-8")),
    )


def document_exists(document_name):
    response = ssm.list_documents(
        Filters=[
            {"Key": "Owner", "Values": ["Self"]},
            {"Key": "DocumentType", "Values": ["Automation"]},
            {"Key": "Name", "Values": [document_name]},
        ]
    )
    document_identifiers = response["DocumentIdentifiers"]
    while "NextToken" in response:
        response = ssm.list_documents(
            Filters=[
                {"Key": "Owner", "Values": ["Self"]},
                {"Key": "DocumentType", "Values": ["Automation"]},
                {"Key": "Name", "Values": [document_name]},
            ],
            NextToken=response["NextToken"],
        )
        document_identifiers.extend(response["DocumentIdentifiers"])
    if len(document_identifiers) == 0:
        return False
    return True


@logger.inject_lambda_context(correlation_id_path=correlation_paths.EVENT_BRIDGE)
@tracer.capture_lambda_handler
# pylint: disable=unused-argument
def handler(event: dict, context: LambdaContext) -> dict:
    print(json.dumps(event))
    document_name = os.environ["STACK_NAME"]
    if event["detail"]["object"]["key"] == os.environ["IPSETS_S3_KEY"]:
        if event["detail-type"] == "Object Created":
            getips_step_id, document = get_document()
            get_object = s3.get_object(
                Bucket=event["detail"]["bucket"]["name"],
                Key=os.environ["IPSETS_S3_KEY"],
            )
            content = json.loads(get_object["Body"].read().decode("utf-8"))
            put_lookups(event["detail"]["bucket"]["name"], get_lookups(content))
            for k, v in get_params(content).items():
                document["parameters"][k] = {
                    "type": "String",
                    "default": "Exclude",
                    "allowedValues": ["Include", "Exclude"],
                }
                for r in v:
                    document["mainSteps"][getips_step_id]["inputs"]["InputPayload"][
                        "IpSets"
                    ][r] = f"{{{{ {k} }}}}"
            print(json.dumps(document))
            if document_exists(document_name):
                logger.info("Update SSM Document")
                # Deleting and recreating to avoid having to different versions
                ssm.delete_document(Name=document_name)
                ssm.create_document(
                    Name=document_name,
                    DocumentType="Automation",
                    DocumentFormat="JSON",
                    TargetType="/AWS::EC2::Instance",
                    Content=json.dumps(document),
                )
            else:
                logger.info("Create SSM Document")
                ssm.create_document(
                    Name=document_name,
                    DocumentType="Automation",
                    DocumentFormat="JSON",
                    TargetType="/AWS::EC2::Instance",
                    Content=json.dumps(document),
                )
        elif event["detail-type"] == "Object Deleted":
            logger.info("Delete SSM Document")
            ssm.delete_document(Name=document_name)
            s3.delete_object(
                Bucket=event["detail"]["bucket"]["name"], Key="lookups/lookups.json.gz"
            )
    return None
