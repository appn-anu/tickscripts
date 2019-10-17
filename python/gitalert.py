#!/usr/bin/env python3
import sys, os
import json
import requests
import datetime
import yaml
import time
import re
from github import Github, GithubObject
import slack
curpath = os.path.abspath(__file__)
mydir = os.path.dirname(curpath)
config = json.load(open(os.path.join(mydir, 'config.json')))
g = Github(config['token'])
user = g.get_organization(config['org'])
repo = user.get_repo(config['repo'])

data = json.load(sys.stdin)

slack_hook = config.get("slack_webhook")

slack_client = slack.WebClient(token=config.get("slack_api_token"))

full_title = "[{}] {}".format(data['level'], data['id'])

r = requests.get("https://raw.githubusercontent.com/appf-anu/tickets/master/schedule.yaml")

no_notify_labels = {'maintenance', 'inactive'}

schedule_data = yaml.safe_load(r.content)

def get_assignees(alert_id):
    def _get_userlist(userlist):
        overrides = schedule_data.get("overrides", list())
        schedules = schedule_data.get("schedules", dict())
        escalation_chains = schedule_data.get("escalation_chains", dict())
        device_services = schedule_data.get("device_services", dict())
        default_services = schedule_data.get("default_services", list())
        days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        day_of_week_i = datetime.datetime.today().weekday()
        day_of_week_str = days_of_week[day_of_week_i]
        
        rusers = set()
        for user in userlist:
            if user in escalation_chains.keys():
                rusers = rusers | get_userlist(escalation_chains[user])
                continue

            if user[-1] == "!":
                user_name = user[:-1]
                if user_name in escalation_chains.keys():
                    forced_users = [x+"!" for x in escalation_chains[user_name]]
                    rusers = rusers | (get_userlist(forced_users))
                else:
                    rusers.add(user_name)

            if user not in schedules.keys():
                rusers.add(user)
                break
            if day_of_week_str in schedules.get(user, "") and user not in overrides:
                rusers.add(user)
                break
        return rusers

    overrides = schedule_data.get("overrides", list())
    schedules = schedule_data.get("schedules", dict())
    escalation_chains = schedule_data.get("escalation_chains", dict())
    device_services = schedule_data.get("device_services", dict())
    default_services = schedule_data.get("default_services", list())
    days_of_week = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_of_week_i = datetime.datetime.today().weekday()
    day_of_week_str = days_of_week[day_of_week_i]

    assignees = set()
    for device, users in device_services.items():
        if device.lower() in alert_id.lower():
            assignees = assignees| _get_userlist(users)
    return assignees

def notify_slack(data, issue=None):
    data_id = data['id']
    data_details = data.get('details', None)
    data_message = data['message']

    slack_users = dict()
    resp = slack_client.users_list()
    if resp['ok']:
        slack_users = {u['name']:u['id'] for u in resp.data['members']}

    color = "#36a64f"
    if "crit" in data['level'].lower():
        color = "#a30200"
    if "off" in data['level'].lower():
        color = "#a30200"
    if "warn" in data['level'].lower():
        color = "#a36500"

    blocks = list()
    blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": full_title+"\n\n"+data_details,
            }
        })

    blocks.append({"type": "divider"})
    blocks.append({"type": "actions", "elements": []})

    if data_details:
        chamberMatch = re.match(r'.*(GC\d\d)', data['id'])
        if chamberMatch is not None:
            chamber = chamberMatch.group()
            link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={host}&orgId=1".format(host=chamber)
            if 'camera' in  data['id'] or 'spc' in data['id']:
                link= "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={host}&orgId=1".format(host=chamber)
            blocks[-1]['elements'].append({
                "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Grafana Dashboard"
                    },
                    "url": link
                })

    if issue is not None:
        section_text = "Ticket link"
        if 'ok' in data['level'].lower() and 'fixed' in [x.name.lower() for x in issue.labels]:
            # close this issue
            issue.edit(state='closed')
            section_text = "Git Ticket Link (closed)"

        blocks[-1]['elements'].append({
                "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": section_text
                    },
                    "url": issue.html_url
                })
        # get the current assignees for the issue
        current_assignees = set([x.login for x in issue.assignees])
        # get their slack ids if they have one in the file:
        userids = [slack_users.get(assignee_name) for assignee_name in current_assignees if slack_users.get(assignee_name)]
        resp = slack_client.conversations_open(users=userids)
        if resp.data['ok'] == True:
            chanid = resp.data['channel']['id']
            slack_client.chat_postMessage(channel=chanid, 
                attachments=[{"color": color,
                              "blocks": blocks}])
    slack_client.chat_postMessage(channel="#alarms", 
                attachments=[{"color": color,
                              "blocks": blocks}])

def make_issue(data):
    data_id = data['id']
    data_message = data['message']
    data_details = data.get('details', None)
    data_level = data['level']

    msg = "### {data_id} \n### {data_message}".format(data_id=data_id, data_message=data_message) 
    if data_details:
        msg += "\n"+data_details
        # no space at the end of regex, we still want to direct user to grafana if its a camera
        chamberMatch = re.match(r'.*(GC\d\d)', data_id)
        if chamberMatch is not None:
            chamber = chamberMatch.group(1)
            link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={}&orgId=1".format(chamber)
            if 'camera' in  data_id or 'spc' in data_id: # if there is camera, then its an spc
                link= "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={}&orgId=1".format(chamber)
            msg += "\n" + "[Dashboard Link]({})".format(link)
    kwargs = {
        "body": msg,
        "labels": [data['level']]
    }
    assignees = get_assignees(data_id)

    if len(assignees) == 1:
        kwargs['assignee'] = assignees.pop()
    if len(assignees) > 1:
        kwargs['assignees'] = ",".join(assignees)

    return repo.create_issue(full_title, **kwargs)


def comment_on_issue(issue, data):
    data_id = data['id']
    data_message = data['message']
    data_details = data.get('details', None)
    data_level = data['level']

    msg = "### {data_id} \n### {data_message}".format(data_id=data_id, data_message=data['message']) 
    if data_details:
        msg += "\n"+data_details
    issue.create_comment(msg)
    # update assignees.
    
    for assignee in get_assignees(data_id):
        issue.add_to_assignees(assignee)

    issue_labels = set(map(lambda x: x.name.lower(), issue.labels))
    if no_notify_labels.isdisjoint(issue_labels) or "fixed" in issue_labels:
        notify_slack(data, issue=issue)
    sys.exit(0)

# main
for issue in repo.get_issues():
    # the space in the regex required to not catch the cameras
    chamberMatch = re.match(r'.*(GC\d\d) ', data['id'])
    if chamberMatch is not None:
        chamber = chamberMatch.group(1)
        if chamber in issue.title:
            comment_on_issue(issue, data)

    if data['id'] in issue.title:
        comment_on_issue(issue, data)

if "ok" in data['level'].lower():
    notify_slack()
    sys.exit(0)
iss = make_issue(data)
notify_slack(issue=iss)
