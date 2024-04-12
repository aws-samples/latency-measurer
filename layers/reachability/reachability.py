import re
from collections import defaultdict


def _ssm_friendly_name(name):
    name_split = re.split("[^a-zA-Z0-9]", name)
    return "".join(map(lambda x: x.capitalize(), name_split))


def get_lookups(reachability):
    return [
        {"ipset": t[0], "Area": t[1], "Location": t[2], "Region": t[3]}
        for t in set(
            [
                (_ssm_friendly_name(r["Region"]), h, p, r["Region"])
                for h, v1 in reachability.items()
                for p, v2 in v1.items()
                for r in v2
            ]
        )
    ]


def get_ipsets(reachability):
    ipsets = defaultdict(lambda: {"ipset": []})
    for r, i in sorted(
        [
            (r["Region"], r["IP"])
            for h in reachability.values()
            for p in h.values()
            for r in p
        ]
    ):
        ipsets[_ssm_friendly_name(r)]["ipset"].append({"ip": i})
    return ipsets


def get_params(reachability):
    params = defaultdict(set)
    for h, v1 in reachability.items():
        for _, v2 in v1.items():
            for r in v2:
                params[_ssm_friendly_name(h)].add(_ssm_friendly_name(r["Region"]))
    return params
