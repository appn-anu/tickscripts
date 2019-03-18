#!/usr/bin/env python3
import sys, os
import json
import requests
import datetime
import yaml
import time
import re
from github import Github, GithubObject
curpath = os.path.abspath(__file__)
mydir = os.path.dirname(curpath)
config = json.load(open(os.path.join(mydir, 'config.json')))
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

def notify_slack(issue=None):
    color = "good"
    if "crit" in data['level'].lower():
        color = "danger"
    if "off" in data['level'].lower():
        color = "danger"
    if "warning" in data['level'].lower():
        color = "warning"

    request_data = {
        "mrkdown_in": ["text"],
        "attachments": [
            {
                "color": color,
                "fallback": data['message'],
                "text": full_title+"\n\n_issue already closed_",
                "footer": "Kapacitor",
                "footer_icon": "https://traitcapture.org/static/img/mascot-kapacitor-transparent_png-16x16.png",
                "ts": time.time()
            }
        ]
    }

    if 'details' in data.keys():
        chamberMatch = re.match(r'(GC\d\d)', data['id'])
        if chamberMatch is not None:
            chamber = chamberMatch.group()
            link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={host}&orgId=1".format(host=chamber)
            if 'camera' in  data['id'] or 'spc' in data['id']:
                link= "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={host}&orgId=1".format(host=chamber)
            attach2 = {
                "color": color,
                "fallback": data['details'],
                "title": "{host} Dashboard Link".format(host=chamber),
                "title_link": link,
                "footer": "Grafana",
                "text": data['details'], 
                "footer_icon": "https://traitcapture.org/static/img/mascot-grafana-transparent_png-16x16.png"
            }
            request_data['attachments'].append(attach2)
    if issue is not None:
        request_data['attachments'][0]['title'] = data['message']
        request_data['attachments'][0]['title_link'] = issue.html_url
        # if this is an ok message and fixed is in the labels
        if 'ok' in data['level'].lower() and 'fixed' in [x.name.lower() for x in issue.labels]:
            # close this issue
            issue.edit(state='closed')
            request_data['attachments'][0]['text'] = full_title+"\n\n_issue closed by appf-bot_"
            if len(request_data['attachments']) > 1:
                request_data['attachments'].pop()
        else:
            del request_data['attachments'][0]['text']

    r = requests.post(
        slack_hook,
        data = json.dumps(request_data),
        headers = {'Content-Type': 'application/json'}
    )

def make_issue():
    msg = "### "+data['message'] 
    if 'details' in data:
        msg += "\n"+data['details']

        chamberMatch = re.match(r'(GC\d\d)', data['id'])
        if chamberMatch is not None:
            chamber = chamberMatch.group()
            link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={}&orgId=1".format(chamber)
            if 'camera' in  data['id'] or 'spc' in data['id']:
                link= "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={}&orgId=1".format(chamber)
            
            msg += "\n" + "[Dashboard Link]({})".format(link)
    kwargs = {
        "body": msg,
        "labels": [data['level']]
    }
    
    if "," in all_assignees:
        kwargs["assignees"] = [x.strip() for x in all_assignees.split(',')]
    else:
        kwargs["assignee"] = all_assignees.strip()

    return repo.create_issue(full_title, **kwargs)

for iss in repo.get_issues():
    if data['id'] in iss.title:
        msg = "### "+data['message'] 
        if 'details' in data:
            msg += "\n"+data['details']
        iss.create_comment(msg)
        notify_slack(issue=iss)
        sys.exit(0)

if "ok" in data['level'].lower():
    notify_slack()
    sys.exit(0)
iss = make_issue()
notify_slack(issue=iss)
