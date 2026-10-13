"""Gera o card de estatísticas do perfil (inclui repositórios privados)."""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

TOKEN = os.environ["GH_TOKEN"]
USER = os.environ.get("GH_USER", "mauriciopcosta")
OUT = sys.argv[1] if len(sys.argv) > 1 else "dist/stats.svg"
IGNORED_LANGS = {"CMake", "Batchfile", "GLSL", "Makefile", "Dockerfile", "Shell", "PowerShell"}
TOP_LANGS = 6


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def contribution_days():
    created = gql("query($u:String!){user(login:$u){createdAt}}", u=USER)["user"]["createdAt"]
    start = datetime.fromisoformat(created.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    days = {}
    while start < now:
        end = min(start + timedelta(days=365), now)
        cal = gql(
            """query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){
              contributionsCollection(from:$f,to:$t){contributionCalendar{
                weeks{contributionDays{date contributionCount}}}}}}""",
            u=USER, f=start.isoformat(), t=end.isoformat(),
        )["user"]["contributionsCollection"]["contributionCalendar"]
        for week in cal["weeks"]:
            for d in week["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
        start = end
    return days


def streaks(days):
    today = max(days)
    longest = run = 0
    d = min(days)
    while d <= today:
        run = run + 1 if days.get(d, 0) > 0 else 0
        longest = max(longest, run)
        d += timedelta(days=1)
    current = 0
    d = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    while days.get(d, 0) > 0:
        current += 1
        d -= timedelta(days=1)
    return current, longest


def languages():
    sizes, colors, cursor = {}, {}, None
    while True:
        data = gql(
            """query($u:String!,$c:String){user(login:$u){repositories(
              first:100,after:$c,ownerAffiliations:OWNER,isFork:false){
              pageInfo{hasNextPage endCursor}
              nodes{languages(first:20){edges{size node{name color}}}}}}}""",
            u=USER, c=cursor,
        )["user"]["repositories"]
        for repo in data["nodes"]:
            for e in repo["languages"]["edges"]:
                name = e["node"]["name"]
                if name in IGNORED_LANGS:
                    continue
                sizes[name] = sizes.get(name, 0) + e["size"]
                colors[name] = e["node"]["color"] or "#8b949e"
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    total = sum(sizes.values()) or 1
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:TOP_LANGS]
    return [(n, s / total * 100, colors[n]) for n, s in top]


def fmt(n):
    return f"{n:,}".replace(",", ".")


def render(kpis, langs):
    w, h = 820, 250
    cells = []
    col_w = (w - 60) / len(kpis)
    for i, (value, label) in enumerate(kpis):
        x = 30 + col_w * i + col_w / 2
        delay = 0.15 * i
        cells.append(
            f'<g class="fade" style="animation-delay:{delay:.2f}s">'
            f'<text x="{x:.1f}" y="88" class="value">{value}</text>'
            f'<text x="{x:.1f}" y="116" class="label">{label}</text></g>'
        )
    bar_x, bar_y, bar_w = 30, 170, w - 60
    segs, legend, offset = [], [], 0.0
    shown = sum(p for _, p, _ in langs) or 1
    for i, (name, pct, color) in enumerate(langs):
        seg_w = bar_w * pct / shown
        segs.append(f'<rect x="{bar_x + offset:.1f}" y="{bar_y}" width="{seg_w:.1f}" height="10" fill="{color}"/>')
        offset += seg_w
        lx = bar_x + (bar_w / len(langs)) * i
        legend.append(
            f'<circle cx="{lx + 6:.1f}" cy="214" r="5" fill="{color}"/>'
            f'<text x="{lx + 16:.1f}" y="218" class="lang">{name} <tspan class="pct">{pct:.1f}%</tspan></text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Estatísticas do GitHub">
<style>
  :root {{ --bg:#ffffff; --border:#d0d7de; --fg:#1f2328; --muted:#59636e; --accent:#0284c7; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#0d1117; --border:#30363d; --fg:#e6edf3; --muted:#8b949e; --accent:#38bdf8; }} }}
  .card {{ fill:var(--bg); stroke:var(--border); }}
  text {{ font-family:'Segoe UI',Ubuntu,Helvetica,Arial,sans-serif; }}
  .value {{ font-size:34px; font-weight:700; fill:var(--accent); text-anchor:middle; }}
  .label {{ font-size:13px; fill:var(--muted); text-anchor:middle; }}
  .title {{ font-size:15px; font-weight:600; fill:var(--fg); }}
  .lang {{ font-size:13px; fill:var(--fg); }}
  .pct {{ fill:var(--muted); }}
  .fade {{ opacity:0; animation:fade .6s ease-out forwards; }}
  .grow {{ transform-origin:{bar_x}px 0; transform:scaleX(0); animation:grow 1s .6s ease-out forwards; }}
  @keyframes fade {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:none; }} }}
  @keyframes grow {{ to {{ transform:scaleX(1); }} }}
</style>
<rect class="card" x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="10"/>
<text x="30" y="36" class="title">Atividade no GitHub</text>
{''.join(cells)}
<text x="30" y="156" class="title">Linguagens mais usadas</text>
<clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath>
<g clip-path="url(#bar)"><g class="grow">{''.join(segs)}</g></g>
<g class="fade" style="animation-delay:1s">{''.join(legend)}</g>
</svg>
"""


def main():
    days = contribution_days()
    today = max(days)
    year_ago = today - timedelta(days=364)
    last_year = {d: c for d, c in days.items() if d >= year_ago}
    current, longest = streaks(days)
    kpis = [
        (fmt(sum(last_year.values())), "Contribuições (12 meses)"),
        (fmt(sum(1 for c in last_year.values() if c > 0)), "Dias ativos (12 meses)"),
        (f"{current} dias", "Sequência atual"),
        (f"{longest} dias", "Maior sequência"),
    ]
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(kpis, languages()))
    print("KPIs:", kpis)


if __name__ == "__main__":
    main()
