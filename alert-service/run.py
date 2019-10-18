#!/usr/bin/env python3
from __future__ import print_function
import sys, os
import json
import requests
import datetime
import yaml
import time
import re
import socketserver

from github import Github, GithubObject
import slack

g = Github(os.getenv("GITHUB_API_TOKEN"))
user = g.get_organization(os.getenv("GITHUB_ORG"))
repo = user.get_repo(os.getenv("GITHUB_REPO"))
slack_client = slack.WebClient(token=os.getenv("SLACK_API_TOKEN"))

no_notify_labels = {'maintenance', 'inactive'}

def datetime_decorator(func):
    def wrapped_func(*args, **kwargs):
        return func(datetime.datetime.now().isoformat(), " - ", *args, **kwargs)
    return wrapped_func

print = datetime_decorator(print)

class TCPAlertHandler(socketserver.BaseRequestHandler):

    def get_assignees(self):
        r = requests.get(os.getenv("SCHEDULE_YAML_URL"))
        schedule_data = yaml.safe_load(r.content)

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
            if device.lower() in self.data['id'].lower():
                assignees = assignees| _get_userlist(users)
        
        self.slackmap = schedule_data.get("slackmap", dict())
        self.assignees = assignees.copy()
        return assignees

    def notify_slack(self):
        data_id = self.data['id']
        data_details = self.data.get('details', None)
        data_message = self.data['message']

        slack_ids = dict()
        resp = slack_client.users_list()
        if resp['ok']:
            slack_ids = {u['name']:u['id'] for u in resp.data['members']}

        color = "#36a64f"
        if "crit" in self.data['level'].lower():
            color = "#a30200"
        if "off" in self.data['level'].lower():
            color = "#a30200"
        if "warn" in self.data['level'].lower():
            color = "#a36500"

        blocks = list()
        blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": data_details,
                }
            })

        blocks.append({"type": "divider"})
        blocks.append({"type": "actions", "elements": []})

        if data_details:
            chamberMatch = re.match(r'.*(GC\d\d)', data_id)
            if chamberMatch is not None:
                chamber = chamberMatch.group()
                link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={host}&orgId=1".format(host=chamber)
                if 'camera' in  data_id or 'spc' in data_id:
                    link= "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={host}&orgId=1".format(host=chamber)
                blocks[-1]['elements'].append({
                    "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Grafana Dashboard"
                        },
                        "url": link
                    })

        if self.issue is not None:
            print("Adding link to ticket to slack alert")
            section_text = "Ticket link"
            if 'ok' in self.data['level'].lower() and 'fixed' in [x.name.lower() for x in self.issue.labels]:
                # close this issue
                issue.edit(state='closed')
                section_text = "Git Ticket Link (closed)"

            blocks[-1]['elements'].append({
                    "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": section_text
                        },
                        "url": self.issue.html_url
                    })
            # get the current assignees for the issue
            current_assignees = set([x.login for x in self.issue.assignees])
            print("Current assignees: ", current_assignees)
            # get their slack ids if they have one in the file:

            slack_logins = [self.slackmap.get(git_login) for git_login in current_assignees if self.slackmap.get(git_login)]
            userids = [slack_ids.get(slack_login) for slack_login in slack_logins if slack_ids.get(slack_login)]
            resp = slack_client.conversations_open(users=userids)
            print("Alerting the following users via dm: ", {k:v for k,v in slack_ids.items() if k in slack_logins})
            if resp.data['ok'] == True:
                chanid = resp.data['channel']['id']
                slack_client.chat_postMessage(channel=chanid, 
                    text=self.full_title,
                    attachments=[{"color": color,
                                  "blocks": blocks}])
        slack_client.chat_postMessage(channel="#alarms", 
                    attachments=[{"color": color,
                                  "blocks": blocks}])

    def get_issue(self):
        # main
        for issue in repo.get_issues():
            # the space in the regex required to not catch the cameras
            chamberMatch = re.match(r'.*(GC\d\d) ', self.data['id'])
            if chamberMatch is not None:
                chamber = chamberMatch.group(1)
                if chamber in issue.title:
                    self.issue = issue
                    print("Found issue: {}".format(self.issue.title))
                    self.comment_on_issue()
                    return
            if self.data['id'] in issue.title:
                self.issue = issue
                print("Found issue: {}".format(self.issue.title))
                self.comment_on_issue()
                return
        else:
            print("Couldn't find existing issue, creating a new one...")
            data_details = self.data.get('details', None)
            msg = "### {data_id} \n### {data_message}".format(data_id=self.data['id'], 
                                                              data_message=self.data['message']) 
            if data_details:
                msg += "\n"+data_details
                # no space at the end of regex, we still want to direct user to grafana if its a camera
                chamberMatch = re.match(r'.*(GC\d\d)', self.data['id'])
                if chamberMatch is not None:
                    chamber = chamberMatch.group(1)
                    link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={}&orgId=1".format(chamber)
                    if 'camera' in  self.data['id'] or 'spc' in self.data['id']: # if there is camera, then its an spc
                        link= "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={}&orgId=1".format(chamber)
                    msg += "\n" + "[Dashboard Link]({})".format(link)
            kwargs = {
                "body": msg,
                "labels": [self.data['level']]
            }
            assignees = self.get_assignees()

            if len(assignees) == 1:
                kwargs['assignee'] = assignees.pop()
            if len(assignees) > 1:
                kwargs['assignees'] = ",".join(assignees)

            self.issue = repo.create_issue(self.full_title, **kwargs)        


    def comment_on_issue(self):
        """
        returns whether slack has been notified or not.
        """
        print("Commenting on issue...")
        data_details = self.data.get('details', None)

        msg = "### {data_id} \n### {data_message}".format(data_id=self.data['id'], 
                                                          data_message=self.data['message']) 
        if data_details:
            msg += "\n"+data_details
        self.issue.create_comment(msg)
        # update assignees.
        for assignee in self.get_assignees():
            self.issue.add_to_assignees(assignee)


    def handle(self):
        self.issue = None
        self.data = None
        # do recv all data
        buf_size = 2**12
        rawdata = ""
        while True:
            part = self.request.recv(buf_size)
            rawdata += part.decode('utf-8')
            if len(part) < buf_size:
                break

        try:
            self.data = json.loads(rawdata)
        except Exception as e:
            self.data = None
            print(e)
            return

        print("Recieved alert json {}".format(self.data))
        self.full_title = "[{}] {}".format(self.data['level'], self.data['id'])
        self.get_issue()

        issue_labels = set(map(lambda x: x.name.lower(), self.issue.labels))
        if no_notify_labels.isdisjoint(issue_labels) or "fixed" in issue_labels:
            self.notify_slack()
        

def main():
    HOST,PORT = "0.0.0.0", 9999
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((HOST, PORT), TCPAlertHandler) as server:
        try:
            print("Started tcp alert server on {}:{}".format(HOST, PORT))
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopping server")
            server.server_close()
        except Exception as e:
            print("Unhandled fatal exception")
            print(e)
            server.server_close()

if __name__ == '__main__':
    main()


