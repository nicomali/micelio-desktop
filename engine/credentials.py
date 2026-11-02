"""
Windows Credential Manager (WinCred) Integration for Micelio Desktop.

Uses both Python's `keyring` library (WinVaultKeyring) and direct `ctypes` binding to
Windows `advapi32.dll` (`CredReadW`, `CredWriteW`, `CredDeleteW`, `CredEnumerateW`)
so Micelio can:
1. Read and write credentials under `micelio-desktop/<key>` in Windows Credential Manager.
2. Read existing generic credentials created externally by Santander scripts or the user
   simply by specifying their target name in Windows Credential Manager.
3. Enumerate saved credentials to display connection status in the Micelio UI without
   ever writing secrets in plain text on disk.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger("micelio.credentials")

SERVICE_PREFIX = "micelio-desktop"

# Standard credential keys managed by Micelio
KNOWN_CREDENTIAL_KEYS = {
    "anthropic_api_key": {
        "label": "Anthropic API Key (Local Testing)",
        "env_fallback": "ANTHROPIC_API_KEY",
        "default_target": f"{SERVICE_PREFIX}/anthropic_api_key",
        "username": "anthropic",
    },
    "github_pat": {
        "label": "GitHub Personal Access Token (MCP GitHub.com)",
        "env_fallback": "GITHUB_PERSONAL_ACCESS_TOKEN",
        "default_target": f"{SERVICE_PREFIX}/github_pat",
        "username": "github",
    },
    "atlassian_api_token": {
        "label": "Atlassian Cloud API Token (MCP Jira & Confluence)",
        "env_fallback": "ATLASSIAN_API_TOKEN",
        "default_target": f"{SERVICE_PREFIX}/atlassian_api_token",
        "username": "atlassian",
    },
    "phoenix_api_key": {
        "label": "Santander Phoenix Token / Secret",
        "env_fallback": "PHOENIX_API_KEY",
        "default_target": f"{SERVICE_PREFIX}/phoenix_api_key",
        "username": "santander-phoenix",
    },
    "aws_access_key_id": {
        "label": "AWS Access Key ID (Boto3 Bedrock / Lambda)",
        "env_fallback": "AWS_ACCESS_KEY_ID",
        "default_target": f"{SERVICE_PREFIX}/aws_access_key_id",
        "username": "aws-key-id",
    },
    "aws_secret_access_key": {
        "label": "AWS Secret Access Key (Boto3 Bedrock / Lambda)",
        "env_fallback": "AWS_SECRET_ACCESS_KEY",
        "default_target": f"{SERVICE_PREFIX}/aws_secret_access_key",
        "username": "aws-secret",
    },
    "aws_session_token": {
        "label": "AWS Session Token (SSO / STS)",
        "env_fallback": "AWS_SESSION_TOKEN",
        "default_target": f"{SERVICE_PREFIX}/aws_session_token",
        "username": "aws-session",
    },
}


# ---------------------------------------------------------------------------
# Native Windows advapi32 WinCred bindings (Zero external dependency fallback)
# ---------------------------------------------------------------------------
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", ctypes.POINTER(wintypes.BYTE)),
    ]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


@dataclass
class CredentialInfo:
    key: str
    label: str
    target_name: str
    username: Optional[str]
    is_configured: bool
    source: str  # "wincred", "env", "none"
    masked_preview: str


class WindowsCredentialVault:
    """
    Reads and writes secrets directly in the Windows Credential Manager (WinCred)
    with fallback to Python `keyring` and environment variables.
    """

    def __init__(self, custom_target_map: Optional[Dict[str, str]] = None) -> None:
        self._is_windows = sys.platform == "win32"
        self._custom_targets: Dict[str, str] = custom_target_map or {}
        self._memory_cache: Dict[str, str] = {}

        if self._is_windows:
            self._advapi32 = ctypes.windll.advapi32
            self._advapi32.CredReadW.argtypes = [
                wintypes.LPWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(PCREDENTIALW),
            ]
            self._advapi32.CredReadW.restype = wintypes.BOOL

            self._advapi32.CredWriteW.argtypes = [
                PCREDENTIALW,
                wintypes.DWORD,
            ]
            self._advapi32.CredWriteW.restype = wintypes.BOOL

            self._advapi32.CredDeleteW.argtypes = [
                wintypes.LPWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
            ]
            self._advapi32.CredDeleteW.restype = wintypes.BOOL

            self._advapi32.CredFree.argtypes = [ctypes.c_void_p]
            self._advapi32.CredFree.restype = None

            self._advapi32.CredEnumerateW.argtypes = [
                wintypes.LPWSTR,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(ctypes.POINTER(PCREDENTIALW)),
            ]
            self._advapi32.CredEnumerateW.restype = wintypes.BOOL

    def set_custom_target(self, key: str, target_name: str) -> None:
        """Map a logical Micelio credential key to an existing Windows Credential target name."""
        if target_name.strip():
            self._custom_targets[key] = target_name.strip()
        else:
            self._custom_targets.pop(key, None)

    def get_target_for_key(self, key: str) -> str:
        if key in self._custom_targets and self._custom_targets[key]:
            return self._custom_targets[key]
        meta = KNOWN_CREDENTIAL_KEYS.get(key)
        if meta:
            return meta["default_target"]
        return f"{SERVICE_PREFIX}/{key}"

    # ------------------------------------------------------------------
    # Low-level WinCred read / write / delete / list
    # ------------------------------------------------------------------
    def read_raw_target(self, target_name: str) -> Optional[ tuple[str, Optional[str]] ]:
        """
        Read a Generic Credential from Windows Credential Manager by its exact TargetName.
        Returns (secret_value, username) or None if not found.
        """
        if not self._is_windows:
            try:
                import keyring
                val = keyring.get_password(SERVICE_PREFIX, target_name)
                return (val, None) if val else None
            except Exception:
                return None

        cred_ptr = PCREDENTIALW()
        ok = self._advapi32.CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr))
        if not ok:
            return None

        try:
            cred = cred_ptr.contents
            username = cred.UserName
            if cred.CredentialBlobSize == 0 or not cred.CredentialBlob:
                return ("", username)
            raw_bytes = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            # Windows Credential Manager stores strings either as UTF-16LE (most Windows UI / WinCred apps)
            # or UTF-8 (some CLI tools). We detect UTF-16LE cleanly if null bytes are interleaved or BOM exists.
            secret = self._decode_blob(raw_bytes)
            return (secret, username)
        finally:
            self._advapi32.CredFree(cred_ptr)

    @staticmethod
    def _decode_blob(raw_bytes: bytes) -> str:
        if not raw_bytes:
            return ""
        # If stored via UTF-16LE (standard Windows Credential Manager GUI & CredWriteW Unicode)
        if len(raw_bytes) % 2 == 0 and (b"\x00" in raw_bytes):
            try:
                return raw_bytes.decode("utf-16-le").rstrip("\x00")
            except UnicodeDecodeError:
                pass
        try:
            return raw_bytes.decode("utf-8").rstrip("\x00")
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1", errors="ignore")

    def write_raw_target(
        self,
        target_name: str,
        secret: str,
        username: str = "micelio-user",
        comment: str = "Managed by Micelio Desktop (Santander Agentic Harness)",
    ) -> bool:
        """Write a secret directly into Windows Credential Manager (UTF-16LE compatible with Windows UI)."""
        self._memory_cache[target_name] = secret
        if not self._is_windows:
            try:
                import keyring
                keyring.set_password(SERVICE_PREFIX, target_name, secret)
                return True
            except Exception as exc:
                logger.warning("Failed to write to keyring: %s", exc)
                return False

        encoded = secret.encode("utf-16-le")
        blob_buffer = (wintypes.BYTE * len(encoded)).from_buffer_copy(encoded)

        cred = CREDENTIALW()
        cred.Flags = 0
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = target_name
        cred.Comment = comment
        cred.CredentialBlobSize = len(encoded)
        cred.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(wintypes.BYTE))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = 0
        cred.Attributes = None
        cred.UserName = username

        ok = self._advapi32.CredWriteW(ctypes.byref(cred), 0)
        if not ok:
            err = ctypes.GetLastError()
            logger.error("WinCred CredWriteW failed for %s with error code %s", target_name, err)
            return False
        return True

    def delete_raw_target(self, target_name: str) -> bool:
        """Remove a credential from Windows Credential Manager."""
        self._memory_cache.pop(target_name, None)
        if not self._is_windows:
            try:
                import keyring
                keyring.delete_password(SERVICE_PREFIX, target_name)
                return True
            except Exception:
                return False

        ok = self._advapi32.CredDeleteW(target_name, CRED_TYPE_GENERIC, 0)
        return bool(ok)

    def enumerate_windows_targets(self, filter_prefix: Optional[str] = None) -> List[Dict[str, str]]:
        """
        List generic credential targets available in Windows Credential Manager
        (returns only TargetName, UserName, and Comment — NEVER returns secret values).
        Useful so the user can pick an existing credential target in the UI!
        """
        if not self._is_windows:
            return []

        count = wintypes.DWORD(0)
        creds_ptr = ctypes.POINTER(PCREDENTIALW)()
        filter_str = f"{filter_prefix}*" if filter_prefix else None

        ok = self._advapi32.CredEnumerateW(
            filter_str,
            0,
            ctypes.byref(count),
            ctypes.byref(creds_ptr),
        )
        if not ok or count.value == 0:
            return []

        results: List[Dict[str, str]] = []
        try:
            for i in range(count.value):
                c = creds_ptr[i].contents
                if c.Type == CRED_TYPE_GENERIC and c.TargetName:
                    results.append(
                        {
                            "target_name": c.TargetName,
                            "username": c.UserName or "",
                            "comment": c.Comment or "",
                        }
                    )
        finally:
            self._advapi32.CredFree(creds_ptr)

        return sorted(results, key=lambda x: x["target_name"].lower())

    # ------------------------------------------------------------------
    # High-level Micelio Credential API
    # ------------------------------------------------------------------
    def get_secret(self, key: str) -> Optional[str]:
        """
        Retrieve a secret by logical key (e.g., 'anthropic_api_key', 'github_pat').
        Priority:
        1. Windows Credential Manager (using custom target name or default `micelio-desktop/<key>`)
        2. Environment variable fallback (e.g. `ANTHROPIC_API_KEY`)
        3. In-memory session cache
        """
        target = self.get_target_for_key(key)
        res = self.read_raw_target(target)
        if res and res[0]:
            return res[0]

        meta = KNOWN_CREDENTIAL_KEYS.get(key)
        if meta and meta.get("env_fallback"):
            env_val = os.environ.get(meta["env_fallback"])
            if env_val:
                return env_val

        return self._memory_cache.get(target)

    def set_secret(
        self,
        key: str,
        secret: str,
        custom_target: Optional[str] = None,
        username: Optional[str] = None,
    ) -> bool:
        """Save a secret into Windows Credential Manager for the given logical key."""
        if custom_target:
            self.set_custom_target(key, custom_target)
        target = self.get_target_for_key(key)
        meta = KNOWN_CREDENTIAL_KEYS.get(key, {})
        user = username or meta.get("username", "micelio")
        return self.write_raw_target(target_name=target, secret=secret, username=user)

    def delete_secret(self, key: str) -> bool:
        target = self.get_target_for_key(key)
        return self.delete_raw_target(target)

    @staticmethod
    def _mask(secret: Optional[str]) -> str:
        if not secret:
            return ""
        if len(secret) <= 8:
            return "*" * len(secret)
        return f"{secret[:4]}{'*' * 8}{secret[-4:]}"

    def list_status(self) -> List[CredentialInfo]:
        """Return safe status metadata for all known Micelio credentials."""
        statuses: List[CredentialInfo] = []
        for key, meta in KNOWN_CREDENTIAL_KEYS.items():
            target = self.get_target_for_key(key)
            raw = self.read_raw_target(target)
            if raw and raw[0]:
                statuses.append(
                    CredentialInfo(
                        key=key,
                        label=meta["label"],
                        target_name=target,
                        username=raw[1] or meta["username"],
                        is_configured=True,
                        source="wincred",
                        masked_preview=self._mask(raw[0]),
                    )
                )
                continue

            env_name = meta.get("env_fallback", "")
            env_val = os.environ.get(env_name) if env_name else None
            if env_val:
                statuses.append(
                    CredentialInfo(
                        key=key,
                        label=meta["label"],
                        target_name=f"ENV:{env_name}",
                        username=meta["username"],
                        source="env",
                        is_configured=True,
                        masked_preview=self._mask(env_val),
                    )
                )
            else:
                statuses.append(
                    CredentialInfo(
                        key=key,
                        label=meta["label"],
                        target_name=target,
                        username=meta["username"],
                        source="none",
                        is_configured=False,
                        masked_preview="",
                    )
                )
        return statuses
