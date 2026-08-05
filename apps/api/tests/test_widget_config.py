"""Widget appearance is unversioned: a save is live, regardless of publish state.

This used to ride `AgentVersion.persona.widget`, so a colour change waited behind the same
approval as a change to what the AI says. It only *looked* instant in testing because a
never-published agent's latest draft and its live version are the same thing by coincidence.
"""

from __future__ import annotations

from httpx import AsyncClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "WidgetOrg"}, headers=_auth(token))
    return {**_auth(token), "X-Org-Id": org.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    agent = await client.post("/v1/agents", json={"name": "Widget Bot"}, headers=headers)
    return str(agent.json()["id"]), str(agent.json()["public_key"])


async def test_a_save_is_live_immediately(client: AsyncClient) -> None:
    headers = await _headers(client, "wc-live@example.com")
    agent_id, key = await _agent(client, headers)

    saved = await client.patch(
        f"/v1/agents/{agent_id}/widget-config", json={"primaryColor": "#123456"}, headers=headers
    )
    assert saved.status_code == 200, saved.text

    # No publish anywhere in between.
    config = await client.get(f"/v1/public/agents/{key}/config")
    assert config.json()["theme"]["primary_color"] == "#123456"


async def test_publish_state_does_not_gate_appearance(client: AsyncClient) -> None:
    """The actual bug: with a real publish history, a colour change used to get stuck."""
    headers = await _headers(client, "wc-publish@example.com")
    agent_id, key = await _agent(client, headers)

    # Give the agent a genuine publish history, so "latest draft" and "live" diverge.
    await client.patch(
        f"/v1/agents/{agent_id}/versions/1", json={"system_prompt": "v1 behaviour"}, headers=headers
    )
    published = await client.post(f"/v1/agents/{agent_id}/versions/1/publish", headers=headers)
    assert published.status_code == 200, published.text

    # An edit now forks an *unpublished* draft (branch-on-edit).
    edited = await client.patch(
        f"/v1/agents/{agent_id}/versions/1", json={"system_prompt": "draft behaviour"}, headers=headers
    )
    assert edited.json()["version"] == 2

    # The colour change still goes live, even though the draft beside it hasn't.
    await client.patch(
        f"/v1/agents/{agent_id}/widget-config", json={"primaryColor": "#ABCDEF"}, headers=headers
    )
    config = (await client.get(f"/v1/public/agents/{key}/config")).json()
    assert config["theme"]["primary_color"] == "#ABCDEF"
    # …while the *behaviour* correctly still serves the published version.
    assert config["welcome_message"]


async def test_saving_appearance_leaves_the_version_persona_alone(client: AsyncClient) -> None:
    """Appearance and behaviour are now genuinely separate stores."""
    headers = await _headers(client, "wc-separate@example.com")
    agent_id, _key = await _agent(client, headers)

    await client.patch(
        f"/v1/agents/{agent_id}/versions/1",
        json={"persona": {"displayName": "Ada", "tone": "warm"}},
        headers=headers,
    )
    await client.patch(
        f"/v1/agents/{agent_id}/widget-config", json={"primaryColor": "#0F0F0F"}, headers=headers
    )

    versions = (await client.get(f"/v1/agents/{agent_id}/versions", headers=headers)).json()
    persona = versions[0]["persona"]
    assert persona["displayName"] == "Ada"
    assert "widget" not in persona or persona.get("widget") in ({}, None), (
        "widget config should no longer be written into the versioned persona"
    )


async def test_partial_saves_merge_rather_than_clobber(client: AsyncClient) -> None:
    headers = await _headers(client, "wc-merge@example.com")
    agent_id, key = await _agent(client, headers)

    await client.patch(
        f"/v1/agents/{agent_id}/widget-config",
        json={"primaryColor": "#111111", "launcherText": "Talk to us"},
        headers=headers,
    )
    # A later save of just one field must not null the other.
    await client.patch(
        f"/v1/agents/{agent_id}/widget-config", json={"logoUrl": "/logo.png"}, headers=headers
    )

    theme = (await client.get(f"/v1/public/agents/{key}/config")).json()["theme"]
    assert theme["primary_color"] == "#111111"
    assert theme["launcher_text"] == "Talk to us"
    assert theme["logo_url"] == "/logo.png"


async def test_bad_values_are_rejected_with_a_typed_error(client: AsyncClient) -> None:
    headers = await _headers(client, "wc-invalid@example.com")
    agent_id, _key = await _agent(client, headers)

    bad = await client.patch(
        f"/v1/agents/{agent_id}/widget-config", json={"primaryColor": "not-a-colour"}, headers=headers
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "widget.invalid_config"


async def test_an_agent_with_no_saved_config_serves_defaults(client: AsyncClient) -> None:
    headers = await _headers(client, "wc-default@example.com")
    _agent_id, key = await _agent(client, headers)
    theme = (await client.get(f"/v1/public/agents/{key}/config")).json()["theme"]
    assert theme["primary_color"] == "#6366F1"  # the shipped default


async def test_appearance_needs_write_but_not_publish(client: AsyncClient) -> None:
    """Making a client wait for review to fix their own branding would be absurd."""
    import re

    from app.core.email import get_email_backend

    owner = await _headers(client, "wc-owner@example.com")
    org_id = owner["X-Org-Id"]
    agent_id, key = await _agent(client, owner)

    await client.post(
        f"/v1/orgs/{org_id}/invitations",
        json={"email": "wc-client@example.com", "role": "editor"},
        headers=owner,
    )
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)
    client_signup = await client.post(
        "/v1/auth/signup", json={"email": "wc-client@example.com", "password": "password123"}
    )
    client_token = client_signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers=_auth(client_token))
    client_headers = {**_auth(client_token), "X-Org-Id": org_id}

    # The client can restyle their own widget…
    ok = await client.patch(
        f"/v1/agents/{agent_id}/widget-config", json={"primaryColor": "#654321"}, headers=client_headers
    )
    assert ok.status_code == 200, ok.text
    assert (await client.get(f"/v1/public/agents/{key}/config")).json()["theme"][
        "primary_color"
    ] == "#654321"

    # …while still not being able to publish behaviour.
    assert (
        await client.post(f"/v1/agents/{agent_id}/versions/1/publish", headers=client_headers)
    ).status_code == 403
