#!/usr/bin/env python3
import sys, os
import json
import gzip
import requests
import datetime
import yaml
import time
import re

curpath = os.path.abspath(__file__)
mydir = os.path.dirname(curpath)
config = json.load(open(os.path.join(mydir, 'config.json')))

# slack_hook = config.get("slack_webhook")
data = json.load(sys.stdin)
os.makedirs(os.path.join("/data/", sys.argv[1]), exist_ok=True)

for series in data['data']['series']:
    header = ",".join(series['columns'])
    pathname = "{}_{}.csv.gz".format((datetime.datetime.now()-datetime.timedelta(hours=24)).strftime("%Y-%m-%d"),series['name'])
    with gzip.open(os.path.join("/data/", sys.argv[1], pathname), 'wt') as f:
        f.write(header+"\n")
        for tp in series['values']:
            f.write(",".join([str(x) for x in tp])+"\n")

