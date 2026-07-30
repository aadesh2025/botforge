"""The four transactional emails BotForge sends, as (subject, text, html) triples.

Deliberately f-strings over a templating engine: four emails don't justify a Jinja
dependency or a template loader, and a reviewer can see the whole email in one place.

**The plain-text part keeps a `Token: <raw>` line.** The dev console outbox is how tests and
the local flow recover a token without a mail server, and a dozen test files parse exactly
that marker. It leaks nothing new — the same token is already in the link on the line above.
The HTML part shows only the button, which is what a real recipient sees.
"""

from __future__ import annotations

from html import escape

_BRAND = "BotForge"

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)
_BODY_STYLE = f"margin:0;padding:24px;background:#f5f5f4;font-family:{_FONT};"
_CARD_STYLE = "max-width:480px;margin:0 auto;background:#ffffff;border-radius:12px;padding:32px;"
_WORDMARK_STYLE = (
    "margin:0 0 24px;font-size:15px;font-weight:700;letter-spacing:-0.01em;color:#1c1917;"
)
_HEADING_STYLE = "margin:0 0 12px;font-size:20px;line-height:1.3;font-weight:650;color:#1c1917;"
_PARAGRAPH_STYLE = "margin:0 0 24px;font-size:14px;line-height:1.6;color:#57534e;"
_BUTTON_STYLE = (
    "display:inline-block;padding:11px 20px;border-radius:8px;background:#e8590c;"
    "color:#ffffff;font-size:14px;font-weight:600;text-decoration:none;"
)
_FOOTER_STYLE = "margin:24px 0 0;font-size:12px;line-height:1.6;color:#a8a29e;"
_FALLBACK_STYLE = (
    "margin:8px 0 0;font-size:12px;line-height:1.6;color:#a8a29e;word-break:break-all;"
)


def _shell(heading: str, paragraph: str, cta_label: str, link: str, footer: str) -> str:
    """One HTML shell for every email: wordmark, heading, paragraph, button, footer.

    Table-free, inline-styled, and system-font — the lowest-common-denominator that survives
    Gmail/Outlook without a build step. Every interpolation is escaped.
    """
    return (
        "<!doctype html>\n"
        "<html>\n"
        f'  <body style="{_BODY_STYLE}">\n'
        f'    <div style="{_CARD_STYLE}">\n'
        f'      <p style="{_WORDMARK_STYLE}">{escape(_BRAND)}</p>\n'
        f'      <h1 style="{_HEADING_STYLE}">{escape(heading)}</h1>\n'
        f'      <p style="{_PARAGRAPH_STYLE}">{escape(paragraph)}</p>\n'
        f'      <a href="{escape(link, quote=True)}" style="{_BUTTON_STYLE}">'
        f"{escape(cta_label)}</a>\n"
        f'      <p style="{_FOOTER_STYLE}">{escape(footer)}</p>\n'
        f'      <p style="{_FALLBACK_STYLE}">Or paste this link into your browser: '
        f"{escape(link)}</p>\n"
        "    </div>\n"
        "  </body>\n"
        "</html>\n"
    )


def invitation_email(org_name: str, role: str, link: str, token: str) -> tuple[str, str, str]:
    subject = f"You're invited to {org_name}"
    text = f"Join {org_name} as {role}: {link}\nToken: {token}"
    html = _shell(
        heading=f"You've been invited to {org_name}",
        paragraph=f"You're invited to join {org_name} on {_BRAND} as {role}. "
        "This invitation expires in 7 days.",
        cta_label="Accept invitation",
        link=link,
        footer="If you weren't expecting this invitation, you can ignore this email.",
    )
    return subject, text, html


def verification_email(link: str, token: str) -> tuple[str, str, str]:
    subject = "Verify your email"
    text = f"Confirm your email: {link}\nToken: {token}"
    html = _shell(
        heading="Confirm your email address",
        paragraph=f"Confirm this address to finish setting up your {_BRAND} account.",
        cta_label="Verify email",
        link=link,
        footer="If you didn't create a BotForge account, you can ignore this email.",
    )
    return subject, text, html


def password_reset_email(link: str, token: str) -> tuple[str, str, str]:
    subject = "Reset your password"
    text = f"Reset your password: {link}\nToken: {token}"
    html = _shell(
        heading="Reset your password",
        paragraph="Choose a new password for your account. This link can only be used once.",
        cta_label="Reset password",
        link=link,
        footer="If you didn't ask for a password reset, you can ignore this email — "
        "your password is unchanged.",
    )
    return subject, text, html


def magic_link_email(link: str, token: str) -> tuple[str, str, str]:
    subject = "Your sign-in link"
    text = f"Sign in: {link}\nToken: {token}"
    html = _shell(
        heading="Your sign-in link",
        paragraph="Use the link below to sign in. It can only be used once, and expires shortly.",
        cta_label="Sign in",
        link=link,
        footer="If you didn't request this link, you can ignore this email.",
    )
    return subject, text, html
