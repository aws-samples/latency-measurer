import json
import urllib3

http = urllib3.PoolManager()


# pylint: disable=unused-argument
def script_handler(events, context):
    print(events)
    secret = json.loads(events["SecretValue"])
    api_key = secret["ApiKeyKey"]
    api_endpoint = events["ApiEndpoint"]
    ipsets = [k for k, v in events["IpSets"].items() if v == "Include"]
    results = []
    for ipset in ipsets:
        response = http.request(
            "GET",
            f"{api_endpoint}/{ipset}",
            headers={"x-api-key": api_key},
        )
        data = json.loads(response.data)
        if "ip" in data:
            results.append("|".join([ipset, data["ip"]]))
    return {"apiKey": api_key, "ips": ",".join(results)}
