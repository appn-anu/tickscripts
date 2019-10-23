#!/usr/bin/env python3
from __future__ import print_function

import os
import json
import requests
import datetime
import yaml
import re
import socketserver
from dateutil import parser
from github import Github
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

days_of_week = ["monday", "tuesday", "wednesday",
                "thursday", "friday", "saturday", "sunday"]


class Person(object):
    def __init__(self, name):
        self.name = name
        self.github_login = None
        self.slack_login = None
        self.slack_id = None
        self.schedule = days_of_week.copy()
        self.override_until = None

    def notify_slack(self):
        pass

    def assign_to_issue(self, issue):
        issue.add_to_assignees(self.git_login)

    @property
    def available(self):
        day_of_week_int = datetime.datetime.today().weekday()
        day_of_week_str = days_of_week[day_of_week_int]
        if day_of_week_str in self.schedule and not self.overridden:
            return True
        return False

    @property
    def overridden(self):
        if self.override_until is None:
            return False
        return datetime.date.today() < self.override_until

    def __repr__(self):
        return "<Person> {} - {}".format(self.name, "available" if self.available else "unavailable")

    @property
    def responsible_people(self):
        # return self in list
        return [self]


class EscalationChain(object):
    def __init__(self, people, unparsed_chain, unparsed_all_chains, flags='', name=None):
        self.name = name
        self.sequence = []  # list of tuples, (Person/EscalationChain, flags)
        for value in unparsed_chain:
            searched = re.search(r'(\w+)([\W]*$)', value)
            if searched is not None:
                name = searched.group(1)
                f = searched.group(2)
                if flags != '':
                    f = flags

                if name in people.keys():
                    self.sequence.append((people[name], f))
                elif name in unparsed_all_chains.keys():
                    chain = EscalationChain(people, unparsed_all_chains[name], unparsed_all_chains,
                                            flags=f,
                                            name=name)
                    self.sequence.append((chain, flags))
                else:
                    print("unknown value {} in EscalationChain: {} ".format(
                        name, self.name))
            else:
                print("failed to regex match {}".format(value))

    def __repr__(self):
        v = "<EscalationChain>: {} {{\n".format(self.name)
        for x in self.sequence:
            v += str(x) + "\n"
        v += "}"
        return v

    @property
    def available(self):
        return True

    @property
    def overridden(self):
        return False

    @property
    def responsible_people(self):
        people = []
        for (item, flags) in self.sequence:

            if "!" in flags:
                people.extend(item.responsible_people)
                continue
            if item.available:
                people.extend(item.responsible_people)
                return people
        return people


def get_schedule_data():
    if os.getenv("DEBUG") == "true":
        return yaml.safe_load(open("schedule.yaml"))
    r = requests.get(os.getenv("SCHEDULE_YAML_URL"))
    return yaml.safe_load(r.content)


def get_all_people(people_data):
    slack_ids = dict()
    resp = slack_client.users_list()
    if resp['ok']:
        slack_ids = {u['name']: u['id'] for u in resp.data['members']}
    else:
        print("wtf, no proper slack ids?")
    people = {}
    for name, yaml_person in people_data.items():
        p = Person(name)
        p.git_login = yaml_person.get("github")
        p.slack_login = yaml_person.get("slack")
        if not p.slack_login:
            temp_slack_id = slack_ids.get(p.git_login)
            if temp_slack_id is not None:
                p.slack_id = temp_slack_id
                p.slack_login = p.git_login
        else:
            p.slack_id = slack_ids.get(p.slack_login)

        override_until = yaml_person.get('override_until')

        if override_until is not None:
            try:
                if type(override_until) is str:
                    p.override_until = parser.parse(override_until).date()
                if type(override_until) is datetime.date:
                    p.override_until = override_until
            except Exception as e:
                print(e)
                p.override_until = None
                pass

        p.schedule = yaml_person.get("schedule", days_of_week.copy())
        people[p.name] = p

    return people


def get_escalation_chains_for_device(device_id, schedule_data, people):
    escalation_chains = schedule_data.get("escalation_chains", dict())
    default_chain = schedule_data.get("default_chain")
    device_services = schedule_data.get('device_services', dict())
    chains = []
    for device, chain in device_services.items():
        if device.lower() in device_id.lower():
            chains.append(EscalationChain(
                people, chain, escalation_chains, name=device))
    if not len(chains):
        chains.append(EscalationChain(
            people, default_chain, escalation_chains, name="DEFAULT-{}".format(device)))
    return chains


class TCPAlertHandler(socketserver.BaseRequestHandler):

    def get_assignees(self):
        r = requests.get(os.getenv("SCHEDULE_YAML_URL"))
        schedule_data = yaml.safe_load(r.content)

        def _get_userlist(userlist):
            overrides = schedule_data.get("overrides", list())
            schedules = schedule_data.get("schedules", dict())
            escalation_chains = schedule_data.get("escalation_chains", dict())
            days_of_week = ["monday", "tuesday", "wednesday",
                            "thursday", "friday", "saturday", "sunday"]
            day_of_week_i = datetime.datetime.today().weekday()
            day_of_week_str = days_of_week[day_of_week_i]

            rusers = set()
            for user in userlist:
                if user in escalation_chains.keys():
                    rusers = rusers | _get_userlist(escalation_chains[user])
                    continue

                if user[-1] == "!":
                    user_name = user[:-1]
                    if user_name in escalation_chains.keys():
                        forced_users = [
                            x + "!" for x in escalation_chains[user_name]]
                        rusers = rusers | (_get_userlist(forced_users))
                    else:
                        rusers.add(user_name)

                if user not in schedules.keys():
                    rusers.add(user)
                    break
                if day_of_week_str in schedules.get(user, "") and user not in overrides:
                    rusers.add(user)
                    break
            return rusers

        device_services = schedule_data.get("device_services", dict())
        assignees = set()
        for device, users in device_services.items():
            if device.lower() in self.data['id'].lower():
                assignees = assignees | _get_userlist(users)

        self.slackmap = schedule_data.get("slackmap", dict())
        self.assignees = assignees.copy()
        return assignees

    def notify_slack(self):
        data_id = self.data['id']
        data_details = self.data.get('details', None)

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

        slack_names = set()
        git_names = set()
        if data_details:
            chamberMatch = re.match(r'.*(GC\d\d)', data_id)
            if chamberMatch is not None:
                chamber = chamberMatch.group()
                link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={host}&orgId=1".format(
                    host=chamber)
                if 'camera' in data_id or 'spc' in data_id:
                    link = "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={host}&orgId=1".format(
                        host=chamber)
                blocks[-1]['elements'].append({
                                              "type": "button",
                                              "url": link,
                                              "text": {
                                                  "type": "plain_text",
                                                  "text": "Grafana Dashboard"
                                              }
                                              })

        notify_ids = set()
        if self.issue:

            print("Adding link to ticket to slack alert")
            section_text = "Ticket link ({})".format(self.issue.state)

            blocks[-1]['elements'].append({
                                          "type": "button",
                                          "url": self.issue.html_url,
                                          "text": {
                                                  "type": "plain_text",
                                                  "text": section_text
                                          }
                                          })
            # get the current assignees for the issue
            current_assignees = set([x.login for x in self.issue.assignees])
            print("Current assignees: ", current_assignees)

            for name, person in self.people.items():
                if person.git_login in current_assignees:
                    notify_ids.add(person.slack_id)
                    slack_names.add(person.name)
                    git_names.add(person.name)

        # get their slack ids if they have one in the file:
        for chain in self.escalation_chains:
            print("Alerting chain {} via slack for these users: {}".format(chain.name,
                                                                           [x.name for x in chain.responsible_people]))

            for person in chain.responsible_people:
                notify_ids.add(person.slack_id)
                slack_names.add(person.name)
        slack_names = [x.title() for x in slack_names]
        git_names = [x.title() for x in git_names]

        context_mrkdown = "*People notified:* {}".format(", ".join(slack_names))
        if len(git_names):
            context_mrkdown = "*Git assignees:* {}\n".format(", ".join(git_names)) + context_mrkdown

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": context_mrkdown
                }
            ]
        })

        resp = slack_client.conversations_open(users=list(notify_ids))
        if resp.data['ok']:
            chanid = resp.data['channel']['id']
            slack_client.chat_postMessage(channel=chanid,
                                          text=self.full_title,
                                          attachments=[{"color": color,
                                                        "blocks": blocks}])
        print("Alerting the slack channel.")
        slack_client.chat_postMessage(channel="#alarms",
                                      text=self.full_title,
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
                msg += "\n" + data_details
                # no space at the end of regex, we still want to direct user to grafana if its a camera
                chamberMatch = re.match(r'.*(GC\d\d)', self.data['id'])
                if chamberMatch is not None:
                    chamber = chamberMatch.group(1)
                    link = "http://grafana.traitcapture.org/d/nonspc/selected-chamber?var-host={}&orgId=1".format(
                        chamber)
                    # if there is camera, then its an spc
                    if 'camera' in self.data['id'] or 'spc' in self.data['id']:
                        link = "http://grafana.traitcapture.org/d/spc/selected-chamber-spc?var-host={}&orgId=1".format(
                            chamber)
                    msg += "\n" + "[Dashboard Link]({})".format(link)
            kwargs = {
                "body": msg,
                "labels": [self.data['level']]
            }

            assignees = set()
            for chain in self.escalation_chains:
                for person in chain.responsible_people:
                    assignees.add(person.git_login)

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
            msg += "\n" + data_details
        self.issue.create_comment(msg)

        for chain in self.escalation_chains:
            for person in chain.responsible_people:
                print("Adding ", person, "to issue {}".format(self.issue.title))
                self.issue.add_to_assignees(person.git_login)

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

        self.schedule_data = get_schedule_data()
        self.people = get_all_people(self.schedule_data['people'])
        self.escalation_chains = get_escalation_chains_for_device(self.data['id'], self.schedule_data, self.people)

        print("Recieved alert json {}".format(self.data))

        print("Running escalation chains {}".format([x.name for x in self.escalation_chains]))

        self.full_title = "[{}] {}".format(self.data['level'], self.data['id'])

        self.get_issue()

        if self.issue is not None:
            if 'ok' in self.data['level'].lower() and 'fixed' in [x.name.lower() for x in self.issue.labels]:
                # close this issue
                self.issue.edit(state='closed')
            issue_labels = set(map(lambda x: x.name.lower(), self.issue.labels))
            if no_notify_labels.isdisjoint(issue_labels) or "fixed" in issue_labels:
                self.notify_slack()
        else:
            self.notify_slack()


def main():
    HOST, PORT = "0.0.0.0", 9999
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
