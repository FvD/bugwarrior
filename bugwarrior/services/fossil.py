import urllib
import urllib2
import cookielib

import re
import six

from jinja2 import Template
from twiggy import log

from bugwarrior.config import asbool, die, get_service_password
from bugwarrior.services import IssueService, Issue


class FossilIssue(Issue):
    SUMMARY = 'fossilsummary'
    URL = 'fossilurl'
    FOREIGN_ID = 'fossilid'
    DESCRIPTION = 'fossildescription'

    UDAS = {
        SUMMARY: {
            'type': 'string',
            'label': 'Fossil Summary'
        },
        URL: {
            'type': 'string',
            'label': 'Fossil URL',
        },
        DESCRIPTION: {
            'type': 'string',
            'label': 'Fossil Description',
        },
        FOREIGN_ID: {
            'type': 'string',
            'label': 'Fossil Issue ID'
        }
    }
    UNIQUE_KEY = (URL, )

    PRIORITY_MAP = {
        'Trivial': 'L',
        'Minor': 'L',
        'Major': 'M',
        'Critical': 'H',
        'Blocker': 'H',
    }

    def to_taskwarrior(self):
        return {
            'project': self.get_project(),
            'priority': self.get_priority(),
            'annotations': self.get_annotations(),
            'tags': self.get_tags(),

            self.URL: self.get_url(),
            self.FOREIGN_ID: self.record['key'],
            self.DESCRIPTION: self.record.get('fields', {}).get('description'),
            self.SUMMARY: self.get_summary(),
        }

    def get_tags(self):
        tags = []

        if not self.origin['import_labels_as_tags']:
            return tags

        context = self.record.copy()
        label_template = Template(self.origin['label_template'])

        for label in self.record.get('fields', {}).get('labels', []):
            context.update({
                'label': label
            })
            tags.append(
                label_template.render(context)
            )

        return tags

    def get_annotations(self):
        return self.extra.get('annotations', [])

    def get_project(self):
        return self.record['key'].rsplit('-', 1)[0]

    def get_number(self):
        return self.record['key'].rsplit('-', 1)[1]

    def get_url(self):
        return self.origin['url'] + '/browse/' + self.record['key']

    def get_summary(self):
        return self.record['fields']['summary']

    def get_priority(self):
        value = self.record['fields'].get('priority')
        if isinstance(value, dict):
            value = value.get('name')
        elif value:
            value = str(value)

        return self.PRIORITY_MAP.get(value, self.origin['default_priority'])

    def get_default_description(self):
        return self.build_default_description(
            title=self.get_summary(),
            url=self.get_processed_url(self.get_url()),
            number=self.get_number(),
            cls='issue',
        )
    

class FossilService(IssueService):
    ISSUE_CLASS = FossilIssue
    CONFIG_PREFIX =  'fossil'
    
    def __init__(self, *args, **kw):
        super(FossilService, self).__init__(*args, **kw)

        self.username = self.config_get('username')
        self.url = self.config_get('url')
        password = self.config_get('password')
        if not password or password.startswith("@oracle:"):
            password = get_service_password(
                self.get_keyring_service(self.config, self.target),
                self.username, oracle=password,
                interactive=self.config.interactive
            )

        self.report_id = self.config_get('report_id')
        self.project_name = self.config_get('project_name')
        self.default_priority = self.config_get('default_priority')

    @classmethod
    def validate_config(cls, config, target):
        for k in ("username", "password", "url"):
            if not config.has_option(target, k):
                die("[%s] has no '%s'" % (target, k))

        IssueService.validate_config(config, target)


    def issues(self):
        issues = self._fetch_tickets()
        log.debug(" Found {0} total.", len(issues))

        issues = [i for i in issues if i["status"] == "Open"]
        log.debug(" Found {0} open.", len(issues))

        return [dict(
            description=self.description(
                issue["title"], issue["url"],
                issue["#"], cls="issue",
            ),
            project=self.project_name,
            priority=self.default_priority,
        ) for issue in issues]

    def _fetch_tickets(self):
        """Returns all remote issues."""
        url = "%srptview?rn=%s&tablist=1" \
            % (self.url, self.report_id)

        jar = cookielib.CookieJar()

        post_data = None

        if self.username is not None and self.password is not None:
            post_data = urllib.urlencode({
                "u": self.username,
                "p": self.password,
                "g": url,
            })
            url = "%slogin" % self.url

        opener = urllib2.build_opener(
            urllib2.HTTPCookieProcessor(jar))
        opener.addheaders = [("User-Agent", "bugwarrior-pull")]

        response = opener.open(url, post_data)
        raw_text = response.read().decode("utf-8")

        tickets, header = [], []
        for line in raw_text.rstrip().split("\n"):
            parts = line.strip().split("\t")
            if not header:
                header = parts
            elif parts:
                ticket = dict(zip(header, parts))
                ticket["url"] = "%stktview/%s" % (self.url, ticket["#"])
                tickets.append(ticket)

        return tickets
