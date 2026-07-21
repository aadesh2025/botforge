"""Widget customization: schema validation, merge-on-write, logo upload, public config."""

from __future__ import annotations

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str = "widget@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "WidgetCo"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> dict:
    r = await client.post("/v1/agents", json={"name": "Widget Bot"}, headers=headers)
    return r.json()


async def test_widget_config_validation(client: AsyncClient) -> None:
    headers = await _headers(client, "wv1@example.com")
    agent = await _agent(client, headers)
    aid, ver = agent["id"], agent["draft_version"]

    # Bad hex → typed 400.
    bad_hex = await client.patch(
        f"/v1/agents/{aid}/versions/{ver}",
        json={"persona": {"widget": {"backgroundColor": "not-a-hex"}}},
        headers=headers,
    )
    assert bad_hex.status_code == 400, bad_hex.text
    assert bad_hex.json()["error"]["code"] == "widget.invalid_config"

    # Bad enum → 400.
    bad_enum = await client.patch(
        f"/v1/agents/{aid}/versions/{ver}",
        json={"persona": {"widget": {"floatingButtonStyle": "triangle"}}},
        headers=headers,
    )
    assert bad_enum.status_code == 400

    # Valid config → 200.
    ok = await client.patch(
        f"/v1/agents/{aid}/versions/{ver}",
        json={
            "persona": {
                "widget": {
                    "primaryColor": "#123456",
                    "widgetStyle": "transparent",
                    "fontFamily": "inter",
                    "floatingButtonStyle": "pulse-ring",
                    "inputBarButtons": ["attachment", "emoji"],
                }
            }
        },
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["persona"]["widget"]["primaryColor"] == "#123456"


async def test_widget_config_merge_on_write(client: AsyncClient) -> None:
    """A partial widget PATCH must not null out previously-set colors, or sibling persona keys."""
    headers = await _headers(client, "wv2@example.com")
    agent = await _agent(client, headers)
    aid, ver = agent["id"], agent["draft_version"]

    # Seed a full widget config + a sibling persona key.
    await client.patch(
        f"/v1/agents/{aid}/versions/{ver}",
        json={
            "persona": {
                "displayName": "Concierge",
                "widget": {"primaryColor": "#AABBCC", "backgroundColor": "#101010", "fontFamily": "georgia"},
            }
        },
        headers=headers,
    )

    # Partial update: just the logo. Everything else must survive.
    patched = await client.patch(
        f"/v1/agents/{aid}/versions/{ver}",
        json={"persona": {"widget": {"logoUrl": "/v1/public/agents/x/widget-logo"}}},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    widget = patched.json()["persona"]["widget"]
    assert widget["logoUrl"] == "/v1/public/agents/x/widget-logo"
    assert widget["primaryColor"] == "#AABBCC"  # preserved
    assert widget["backgroundColor"] == "#101010"  # preserved — NOT nulled
    assert widget["fontFamily"] == "georgia"  # preserved
    assert patched.json()["persona"]["displayName"] == "Concierge"  # sibling key preserved


async def test_public_config_exposes_extended_theme(client: AsyncClient) -> None:
    headers = await _headers(client, "wv3@example.com")
    agent = await _agent(client, headers)
    aid, ver, pk = agent["id"], agent["draft_version"], agent["public_key"]
    await client.patch(
        f"/v1/agents/{aid}/versions/{ver}",
        json={"persona": {"widget": {"widgetStyle": "transparent", "textColor": "#ABCDEF", "fontFamily": "courier"}}},
        headers=headers,
    )
    await client.post(f"/v1/agents/{aid}/versions/{ver}/publish", headers=headers)

    cfg = await client.get(f"/v1/public/agents/{pk}/config")
    assert cfg.status_code == 200, cfg.text
    theme = cfg.json()["theme"]
    assert theme["widget_style"] == "transparent"
    assert theme["text_color"] == "#ABCDEF"
    assert theme["font_family"] == "courier"
    assert theme["input_bar_buttons"] == ["attachment"]  # default
    # Unconfigured fields keep today's defaults.
    assert theme["primary_color"] == "#E8590C"
    assert theme["floating_button_style"] is None


# A 1x1 transparent PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c6360000002000100" "05fe02fea7a3a0e40000000049454e44ae426082"
)


async def test_widget_logo_upload_and_serve(client: AsyncClient) -> None:
    headers = await _headers(client, "wv4@example.com")
    agent = await _agent(client, headers)
    aid, ver, pk = agent["id"], agent["draft_version"], agent["public_key"]

    # SVG is rejected (stored-XSS risk) even with an image content-type.
    svg = await client.post(
        f"/v1/agents/{aid}/widget/logo",
        files={"file": ("logo.svg", b"<svg/>", "image/svg+xml")},
        headers=headers,
    )
    assert svg.status_code == 400 and svg.json()["error"]["code"] == "widget.logo_svg_rejected"

    # A .png with a spoofed non-image content-type is rejected (extension check).
    spoof = await client.post(
        f"/v1/agents/{aid}/widget/logo",
        files={"file": ("logo.txt", _PNG, "text/plain")},
        headers=headers,
    )
    assert spoof.status_code == 400

    # A real PNG is accepted and returns a public URL.
    up = await client.post(
        f"/v1/agents/{aid}/widget/logo",
        files={"file": ("logo.png", _PNG, "image/png")},
        headers=headers,
    )
    assert up.status_code == 200, up.text
    logo_url = up.json()["logo_url"]
    assert logo_url == f"/v1/public/agents/{pk}/widget-logo"

    # Store it on the version + publish, then the public serve endpoint returns the image.
    await client.patch(
        f"/v1/agents/{aid}/versions/{ver}", json={"persona": {"widget": {"logoUrl": logo_url}}}, headers=headers
    )
    await client.post(f"/v1/agents/{aid}/versions/{ver}/publish", headers=headers)

    served = await client.get(f"/v1/public/agents/{pk}/widget-logo")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.content == _PNG
