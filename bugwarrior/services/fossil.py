import urllib
import urllib2
import cookielib

from twiggy import log

from bugwarrior.services import IssueService
from bugwarrior.config import die


class FossilService(IssueService):
    def __init__(self, *args, **kw):
        super(FossilService, self).__init__(*args, **kw)

        defaults = {
            "url": None,
            "username": None,
            "password": None,
            "report_id": 1,
            "project_name": None,
            "default_priority": "M",
        }

        for k, v in defaults.items():
            if self.config.has_option(self.target, k):
                v = self.config.get(self.target, k)
            setattr(self, k, v)

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
