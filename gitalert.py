#!/usr/bin/env python3
import sys
import json
import requests
import datetime
import yaml
import time
from github import Github, GithubObject
config = json.load(open('/home/gareth/tickscripts/config.json'))
g = Github(config['token'])

user = g.get_organization(config['org'])
repo = user.get_repo(config['repo'])
data = json.load(sys.stdin)

slack_hook = config.get("slack_webhook")

full_title = "[{}] {}".format(data['level'], data['id'])

day_of_week = datetime.datetime.today().weekday()
r = requests.get("https://raw.githubusercontent.com/appf-anu/tickets/master/schedule.yaml")

schedule_data = yaml.load(r.content)

always = None

if type(schedule_data['notify_always']) is list:
    always = ",".join(schedule_data['notify_always'])
elif type(schedule_data['notify_always']) is str:
    always = schedule_data['notify_always'].strip()

all_assignees = schedule_data['notify_on_days'][day_of_week]

if always is not None and always not in ["", ",", " "]:
    all_assignees = ",".join([always, schedule_data['notify_on_days'][day_of_week]])

def notify_slack(issue):

    color = "good"
    if "critical" in data['level'].lower():
        color = "danger"
    if "warning" in data['level'].lower():
        color = "warning"

    request_data = {
        "mrkdown_in": ["text"],
        "attachments": [
            {
                "fallback": data['message'],
                "color": color,
                "pretext": data['id'],
                "title": issue.title,
                "title_link": issue.html_url,
                "text": data['message'],
                "footer": "Kapacitor",
                "footer_icon": "https://traitcapture.org/static/img/mascot-kapacitor-transparent_png-16x16.png",
                "ts": time.time()
            }
        ]
    }
    r = requests.post(
        slack_hook,
        data = json.dumps(request_data),
        headers = {'Content-Type': 'application/json'}
    )

def make_issue():
    kwargs = {
        "body": data['message'],
        "labels": [data['level']]
    }

    if "," in all_assignees:
        kwargs["assignees"] = [x.strip() for x in all_assignees.split(',')]
    else:
        kwargs["assignee"] = all_assignees.strip()

    return repo.create_issue(full_title, **kwargs)

for iss in repo.get_issues():
    if data['id'] in iss.title:
        iss.create_comment(data['message'])
        notify_slack(iss)
        sys.exit(0)

iss = make_issue()
notify_slack(iss)
