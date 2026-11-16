"""Refresh the stats block in README.md with live GitHub data.

Grade uses the github-readme-stats rank formula, scoring activity only (stars and
followers are left out on purpose). Levels: the standard S..C, plus a custom S++ for
the top 0.1%.
"""
import json, os, re, sys, urllib.request

USER = "bardrop"
# Orgs that are the user's own or team work; not counted as outside open source.
OWN_ORGS = ["bardrop", "bardrop-oss", "accoladehq", "dealmeridian",
            "technex-iit-bhu", "IIT-BHU-SPORTS-FEST", "VibeSocial"]
TOKEN = os.environ["STATS_TOKEN"]
HDR = {"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats",
       "Accept": "application/vnd.github+json"}


def call(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=HDR)
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if "errors" in out:
        sys.exit(f"GitHub error: {out['errors']}")
    return out


def gql(query, **variables):
    return call("https://api.github.com/graphql", {"query": query, "variables": variables})["data"]


def search_count(q):
    return gql("query($q:String!){search(query:$q,type:ISSUE,first:1){issueCount}}", q=q)["search"]["issueCount"]


def outside_merged():
    """Merged PRs in repos outside OWN_ORGS, with each repo's star count."""
    q = f"is:pr author:{USER} is:merged " + " ".join(f"-user:{o}" for o in OWN_ORGS)
    prs, after = [], None
    while True:
        d = gql("""query($q:String!,$after:String){search(query:$q,type:ISSUE,first:100,after:$after){
                   pageInfo{hasNextPage endCursor}
                   nodes{... on PullRequest{repository{nameWithOwner stargazerCount}}}}}""",
                q=q, after=after)["search"]
        prs += [n["repository"] for n in d["nodes"] if n]
        if not d["pageInfo"]["hasNextPage"]:
            return prs
        after = d["pageInfo"]["endCursor"]


def rank(commits, prs, issues, reviews):
    exp = lambda x: 1 - 2 ** -x
    parts = [(2, exp(commits / 250)), (3, exp(prs / 50)), (1, exp(issues / 25)), (1, exp(reviews / 2))]
    r = 1 - sum(w * v for w, v in parts) / sum(w for w, _ in parts)
    levels = ["S++", "S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    cuts = [0.1, 1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    return next(l for l, c in zip(levels, cuts) if r * 100 <= c), r * 100


def main():
    u = gql("""query($u:String!){user(login:$u){
        pullRequests{totalCount} issues{totalCount}
        repositoriesContributedTo(contributionTypes:[COMMIT,PULL_REQUEST,ISSUE]){totalCount}
        contributionsCollection{totalCommitContributions totalPullRequestReviewContributions
          contributionCalendar{totalContributions}}}}""", u=USER)["user"]
    cc = u["contributionsCollection"]
    s = {
        "prs": u["pullRequests"]["totalCount"],
        "merged": search_count(f"is:pr author:{USER} is:merged"),
        "issues": u["issues"]["totalCount"],
        "repos": u["repositoriesContributedTo"]["totalCount"],
        "commits_all": call(f"https://api.github.com/search/commits?q=author:{USER}&per_page=1")["total_count"],
        "commits_year": cc["totalCommitContributions"],
        "contribs": cc["contributionCalendar"]["totalContributions"],
        "reviews": cc["totalPullRequestReviewContributions"],
    }
    outside = outside_merged()
    stars_by_repo = {r["nameWithOwner"]: r["stargazerCount"] for r in outside}
    s["oss_merged"] = len(outside)
    s["oss_repos"] = len(stars_by_repo)
    s["big_repos"] = sum(1 for v in stars_by_repo.values() if v >= 1000)
    s["grade"], s["pct"] = rank(s["commits_year"], s["prs"], s["issues"], s["reviews"])
    print(json.dumps(s, indent=1))

    f = lambda n: f"{n:,}"
    # One tile per stat: big number on top, small label under it, in the same cell.
    def tile(value, label):
        return f'<td align="center" width="25%"><h3>{value}</h3><sub>{label}</sub></td>'

    rows = [
        [tile(f"🏅 {s['grade']}", "activity grade"), tile(f(s["prs"]), "PRs opened"),
         tile(f(s["merged"]), "PRs merged"), tile(f(s["commits_all"]), "commits")],
        [tile(f(s["contribs"]), "contributions (1 yr)"), tile(f(s["issues"]), "issues opened"),
         tile(f(s["repos"]), "repos contributed to"),
         tile(f(s["oss_merged"]), "OSS PRs merged")],
    ]
    block = "<table>\n" + "".join("<tr>" + "".join(r) + "</tr>\n" for r in rows) + "</table>\n"
    path = os.environ.get("README", "README.md")
    text = open(path).read()
    new = re.sub(r"(<!-- STATS:START -->\n).*?(<!-- STATS:END -->)", lambda m: m[1] + block + m[2], text, flags=re.S)
    if new == text and "<!-- STATS:START -->" not in text:
        sys.exit("STATS markers not found in README")
    open(path, "w").write(new)


if __name__ == "__main__":
    main()
