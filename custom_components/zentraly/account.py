"""Shared Zentraly API instances per account (credentials from config entries)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import ZentralyAPI
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN


def get_or_create_api(hass: HomeAssistant, entry: ConfigEntry) -> ZentralyAPI:
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    domain_data = hass.data.setdefault(DOMAIN, {})
    shared_apis = domain_data.setdefault("_shared_apis", {})
    refcounts = domain_data.setdefault("_account_refcounts", {})

    api = shared_apis.get(email)
    if api is None:
        api = ZentralyAPI(email=email, password=password)
        shared_apis[email] = api
        refcounts[email] = refcounts.get(email, 0)
        return api

    api.update_credentials(email, password)
    return api


def update_stored_credentials_for_account(
    hass: HomeAssistant,
    previous_email: str,
    *,
    new_email: str,
    new_password: str,
) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    shared_apis = domain_data.get("_shared_apis", {})
    refcounts = domain_data.get("_account_refcounts", {})
    keepalive_unsubs = domain_data.get("_keepalive_unsubs", {})

    api = shared_apis.pop(previous_email, None)
    refcount = refcounts.pop(previous_email, 0)
    keepalive_unsub = keepalive_unsubs.pop(previous_email, None)

    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if config_entry.data.get(CONF_EMAIL) != previous_email:
            continue
        hass.config_entries.async_update_entry(
            config_entry,
            data={
                **config_entry.data,
                CONF_EMAIL: new_email,
                CONF_PASSWORD: new_password,
            },
        )

    if api is not None:
        api.update_credentials(new_email, new_password)
        shared_apis[new_email] = api
    if refcount:
        refcounts[new_email] = refcount
    if keepalive_unsub is not None:
        keepalive_unsubs[new_email] = keepalive_unsub
