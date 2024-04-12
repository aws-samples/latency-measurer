import json
import os
from collections import defaultdict

import boto3
import requests
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from lxml import etree

tracer = Tracer()
logger = Logger()

s3 = boto3.client("s3")


@logger.inject_lambda_context(correlation_id_path=correlation_paths.EVENT_BRIDGE)
@tracer.capture_lambda_handler
# pylint: disable=unused-argument
def handler(event: dict, context: LambdaContext) -> dict:
    response = requests.get(os.environ["URL"], timeout=30)
    # pylint: disable=c-extension-no-member
    html = etree.HTML(response.text)
    panel_headings = html.xpath('//div[@class="panel-heading"]')
    heading = ""
    reachability = defaultdict(lambda: defaultdict(list))
    for ph in panel_headings:
        heading = ph.find("h3").text
        tbody = ph.getnext().find("table").find("tbody")
        location = ""
        columns = []
        for tr in tbody:
            if tr[0].tag == "th" and len(tr) == 1:
                location = tr[0].text
            elif tr[0].tag == "th" and len(tr) > 1:
                columns = tr
            else:
                record = {}
                for i, td in enumerate(tr):
                    if td.text:
                        record[columns[i].text] = td.text
                reachability[heading][location].append(record)
    s3.put_object(
        Bucket=os.environ["BUCKET_NAME"],
        Key=os.environ["OUTPUT_KEY"],
        Body=json.dumps(reachability),
    )
