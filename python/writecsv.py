#!/usr/bin/env python3
import sys, os
import json
import requests
import datetime
import yaml
import time
import re

curpath = os.path.abspath(__file__)
mydir = os.path.dirname(curpath)
config = json.load(open(os.path.join(mydir, 'config.json')))

slack_hook = config.get("slack_webhook")
data = json.load(sys.stdin)
for series in data['data']['series']:
    header = ",".join(series['columns'])
    with open("/data/{}_{}.csv".format((datetime.datetime.now()-datetime.timedelta(hours=24)).strftime("%Y-%m-%d"),series['name']), 'w') as f:
        f.write(header+"\n")
        for tp in series['values']:
            f.write(",".join([str(x) for x in tp])+"\n")
