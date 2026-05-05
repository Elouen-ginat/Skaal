"""
Team directory example demonstrating native secondary-index queries.

Run locally:

    skaal run examples.team_directory:app

Seed the fixture data:

    curl -s localhost:8000/seed_directory -X POST | jq

Query a paged leaderboard for one team:

    curl -s 'localhost:8000/team_leaderboard?team=alpha&limit=2' | jq

Use the returned cursor to fetch the next page:

    curl -s 'localhost:8000/team_leaderboard?team=alpha&limit=2&cursor=<cursor>' | jq

Lookup a member through the unique email index:

    curl -s 'localhost:8000/find_member?email=mina@example.com' | jq
"""

from __future__ import annotations

from pydantic import BaseModel

from skaal import App, SecondaryIndex, Store

app = App("team-directory")


class TeamMember(BaseModel):
    id: str
    team: str
    score: int
    email: str
    role: str
    region: str


FIXTURE_MEMBERS = [
    TeamMember(
        id="m1",
        team="alpha",
        score=18,
        email="alex@example.com",
        role="captain",
        region="us-east",
    ),
    TeamMember(
        id="m2",
        team="alpha",
        score=7,
        email="mina@example.com",
        role="analyst",
        region="eu-west",
    ),
    TeamMember(
        id="m3",
        team="alpha",
        score=25,
        email="sam@example.com",
        role="engineer",
        region="us-west",
    ),
    TeamMember(
        id="m4",
        team="alpha",
        score=11,
        email="ivy@example.com",
        role="support",
        region="ap-south",
    ),
    TeamMember(
        id="m5",
        team="beta",
        score=30,
        email="nora@example.com",
        role="captain",
        region="us-east",
    ),
    TeamMember(
        id="m6",
        team="beta",
        score=16,
        email="li@example.com",
        role="engineer",
        region="eu-central",
    ),
    TeamMember(
        id="m7",
        team="gamma",
        score=21,
        email="omar@example.com",
        role="captain",
        region="me-central",
    ),
    TeamMember(
        id="m8",
        team="gamma",
        score=9,
        email="zoe@example.com",
        role="designer",
        region="us-west",
    ),
]


@app.storage(
    read_latency="< 10ms",
    durability="persistent",
    access_pattern="random-read",
    indexes=[
        SecondaryIndex(name="by_team", partition_key="team", sort_key="score"),
        SecondaryIndex(name="by_email", partition_key="email", unique=True),
    ],
)
class TeamMembers(Store[TeamMember]):
    """Directory entries backed by KV storage with native secondary indexes."""


@app.function()
async def seed_directory() -> dict:
    for member in FIXTURE_MEMBERS:
        await TeamMembers.set(member.id, member)
    return {"seeded": len(FIXTURE_MEMBERS)}


@app.function()
async def team_leaderboard(team: str, limit: int = 3, cursor: str | None = None) -> dict:
    page = await TeamMembers.query_index("by_team", team, limit=limit, cursor=cursor)
    return {
        "team": team,
        "items": [member.model_dump() for member in page.items],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


@app.function()
async def find_member(email: str) -> dict:
    page = await TeamMembers.query_index("by_email", email, limit=1)
    member = page.items[0] if page.items else None
    return {"member": member.model_dump() if member is not None else None}
