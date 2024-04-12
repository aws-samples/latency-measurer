import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


sec_client = boto3.client("secretsmanager")
agw_client = boto3.client("apigateway")


# pylint: disable=unused-argument
def handler(event, context):
    arn = event["SecretId"]
    token = event["ClientRequestToken"]
    step = event["Step"]

    metadata = sec_client.describe_secret(SecretId=arn)
    if not metadata["RotationEnabled"]:
        logger.error(f"Secret {arn} is not enabled for rotation")
        raise ValueError(f"Secret {arn} is not enabled for rotation")
    versions = metadata["VersionIdsToStages"]
    if token not in versions:
        logger.error(
            f"Secret version {token} has no stage for rotation of secret {arn}."
        )
        raise ValueError(
            f"Secret version {token} has no stage for rotation of secret {arn}."
        )
    if "AWSCURRENT" in versions[token]:
        logger.info(
            f"Secret version {token} already set as AWSCURRENT for secret {arn}."
        )
        return
    elif "AWSPENDING" not in versions[token]:
        logger.error(
            f"Secret version {token} not set as AWSPENDING for rotation of secret {arn}."
        )
        raise ValueError(
            f"Secret version {token} not set as AWSPENDING for rotation of secret {arn}."
        )

    if step == "createSecret":
        create_secret(arn, token)

    elif step == "setSecret":
        set_secret(arn, token)

    elif step == "testSecret":
        test_secret(arn, token)

    elif step == "finishSecret":
        finish_secret(arn, token)

    else:
        raise ValueError("Invalid step parameter")


def create_secret(arn, token):
    current_value = sec_client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    try:
        sec_client.get_secret_value(
            SecretId=arn, VersionId=token, VersionStage="AWSPENDING"
        )
        logger.info(f"createSecret: Successfully retrieved secret for {arn}.")
    except sec_client.exceptions.ResourceNotFoundException:
        secret = json.loads(current_value["SecretString"])
        usage_plan_Id = secret["UsagePlanId"]
        create_api_key = agw_client.create_api_key(enabled=True)
        api_key_id = create_api_key["id"]
        agw_client.create_usage_plan_key(
            usagePlanId=usage_plan_Id, keyId=api_key_id, keyType="API_KEY"
        )
        logger.info(f"createApiKey: Successfully created api key {api_key_id}.")

        sec_client.put_secret_value(
            SecretId=arn,
            ClientRequestToken=token,
            SecretString=json.dumps(
                {
                    "UsagePlanId": usage_plan_Id,
                    "ApiKeyId": create_api_key["id"],
                    "ApiKeyKey": create_api_key["value"],
                }
            ),
            VersionStages=["AWSPENDING"],
        )
        logger.info(
            f"createSecret: Successfully put secret for ARN {arn} and version {token}."
        )


def set_secret(arn, token):
    return


def test_secret(arn, token):
    return


def finish_secret(arn, token):
    metadata = sec_client.describe_secret(SecretId=arn)
    current_version = None
    for version in metadata["VersionIdsToStages"]:
        if "AWSCURRENT" in metadata["VersionIdsToStages"][version]:
            if version == token:
                logger.info(
                    f"finishSecret: Version {version} already marked as AWSCURRENT for {arn}"
                )
                return
            current_version = version
            break

    current_value = sec_client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    secret = json.loads(current_value["SecretString"])
    usage_plan_Id = secret["UsagePlanId"]
    api_key_id = secret["ApiKeyId"]

    sec_client.update_secret_version_stage(
        SecretId=arn,
        VersionStage="AWSCURRENT",
        MoveToVersionId=token,
        RemoveFromVersionId=current_version,
    )
    logger.info(
        f"finishSecret: Successfully set AWSCURRENT stage to version {token} for secret {arn}."
    )

    if api_key_id != "":
        agw_client.delete_usage_plan_key(usagePlanId=usage_plan_Id, keyId=api_key_id)
        agw_client.delete_api_key(apiKey=api_key_id)
        logger.info(f"deleteApiKey: Successfully delete api key {api_key_id}.")
