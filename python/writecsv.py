#!/usr/bin/env python3
import sys, os
import json
import requests
import datetime
import yaml
import time
import re
slack_hook = config.get("slack_webhook")
curpath = os.path.abspath(__file__)
mydir = os.path.dirname(curpath)
config = json.load(open(os.path.join(mydir, 'config.json')))

data = json.load(sys.stdin)

slack_hook = config.get("slack_webhook")
with open("/data/test-{}.json".format(datetime.datetime.now().isoformat()), 'w') as f:
    json.dumps(data, f, indent=4)
