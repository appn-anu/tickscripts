#!/usr/bin/env python3
import sys
import json
from github import Github, GithubObject
config = json.load(open('/home/gareth/tickscripts/config.json'))
g = Github(config['token'])

user = g.get_organization(config['org'])
repo = user.get_repo(config['repo'])
data = json.load(sys.stdin)

full_title = "[{}] {}".format(data['level'], data['id'])

def make_issue():
    kwargs = {
        "body": data['message'],
        "labels": [data['level']]
    }
    if "," in sys.argv[1]:
        kwargs["assignees"] = sys.argv[1].split(',')
    else:
        kwargs["assignee"] = sys.argv[1].strip()

    repo.create_issue(full_title, **kwargs)

for iss in repo.get_issues():
    if data['id'] in iss.title:
        iss.create_comment(data['message'])
        sys.exit(0)

make_issue()
