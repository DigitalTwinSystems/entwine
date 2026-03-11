"""Factory for creating platform adapters — real or stub based on available credentials."""

from __future__ import annotations

import structlog

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.linkedin import LinkedInSimAdapter
from entwine.platforms.registry import PlatformRegistry
from entwine.platforms.settings import PlatformSettings
from entwine.platforms.stubs import (
    EmailAdapter,
    GitHubAdapter,
    SlackAdapter,
    XAdapter,
)

log = structlog.get_logger(__name__)


def _try_slack(settings: PlatformSettings) -> PlatformAdapter:
    if settings.slack.bot_token:
        try:
            from entwine.platforms.slack import SlackLiveAdapter

            adapter = SlackLiveAdapter(settings.slack)
            log.info("factory.adapter", platform="slack", mode="live")
            return adapter
        except ImportError:
            log.warning("factory.missing_dep", platform="slack", package="slack-sdk")
    log.info("factory.adapter", platform="slack", mode="stub")
    return SlackAdapter()


def _try_github(settings: PlatformSettings) -> PlatformAdapter:
    if settings.github.token and settings.github.owner and settings.github.repo:
        from entwine.platforms.github import GitHubLiveAdapter

        log.info("factory.adapter", platform="github", mode="live")
        return GitHubLiveAdapter(settings.github)
    log.info("factory.adapter", platform="github", mode="stub")
    return GitHubAdapter()


def _try_email(settings: PlatformSettings) -> PlatformAdapter:
    if settings.email.credentials_json and settings.email.token_json:
        try:
            from entwine.platforms.email import EmailLiveAdapter

            adapter = EmailLiveAdapter(settings.email)
            log.info("factory.adapter", platform="email", mode="live")
            return adapter
        except ImportError:
            log.warning(
                "factory.missing_dep",
                platform="email",
                package="google-api-python-client / google-auth-oauthlib",
            )
        except Exception:
            log.exception("factory.email_auth_failed")
    log.info("factory.adapter", platform="email", mode="stub")
    return EmailAdapter()


def _try_x(settings: PlatformSettings) -> PlatformAdapter:
    if settings.x.bearer_token or (settings.x.api_key and settings.x.access_token):
        try:
            from entwine.platforms.x import XLiveAdapter

            adapter = XLiveAdapter(settings.x)
            log.info("factory.adapter", platform="x", mode="live")
            return adapter
        except ImportError:
            log.warning("factory.missing_dep", platform="x", package="tweepy")
    log.info("factory.adapter", platform="x", mode="stub")
    return XAdapter()


def build_platform_registry(
    settings: PlatformSettings | None = None,
) -> PlatformRegistry:
    """Create a :class:`PlatformRegistry` with best-available adapters.

    When credentials are configured and the SDK is installed, real adapters are
    used. Otherwise, stub adapters provide simulated responses.

    LinkedIn is always simulated per ADR-006.
    """
    if settings is None:
        settings = PlatformSettings()

    registry = PlatformRegistry()

    registry.register(_try_slack(settings))
    registry.register(_try_github(settings))
    registry.register(_try_email(settings))
    registry.register(_try_x(settings))
    # LinkedIn: always simulated (ADR-006).
    registry.register(LinkedInSimAdapter())

    return registry
