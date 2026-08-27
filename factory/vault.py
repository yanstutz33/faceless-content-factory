from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SecureVault:
    """Encrypted local vault with DPAPI and an ACL-protected Fernet fallback."""

    entropy = b"faceless-content-factory:v1"

    def __init__(self, path: Path):
        self.path = path
        self.key_path = path.with_suffix(".key")
        self.lock = threading.RLock()

    @property
    def available(self) -> bool:
        return True

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(data)
        return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    def _crypt_dpapi(self, data: bytes, protect: bool) -> bytes:
        if os.name != "nt":
            raise RuntimeError("DPAPI indisponível neste sistema")
        source, source_buffer = self._blob(data)
        entropy, entropy_buffer = self._blob(self.entropy)
        output = _DataBlob()
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR,
                                             ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                             wintypes.DWORD, ctypes.POINTER(_DataBlob)]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR),
                                               ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                                               wintypes.DWORD, ctypes.POINTER(_DataBlob)]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        description = wintypes.LPWSTR()
        if protect:
            ok = crypt32.CryptProtectData(ctypes.byref(source), "Faceless Factory", ctypes.byref(entropy),
                                          None, None, 1, ctypes.byref(output))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description), ctypes.byref(entropy),
                                            None, None, 1, ctypes.byref(output))
        _ = (source_buffer, entropy_buffer)
        if not ok:
            raise RuntimeError(f"O Windows não conseguiu acessar o cofre local (código {ctypes.get_last_error()})")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32.LocalFree(output.pbData)
            if description:
                kernel32.LocalFree(description)

    def _restrict_key(self) -> None:
        os.chmod(self.key_path, 0o600)
        if os.name != "nt":
            return
        identity = subprocess.run(
            ["whoami"], capture_output=True, text=True, check=False
        )
        username = identity.stdout.strip() if identity.returncode == 0 else ""
        if not username:
            raise RuntimeError("Não foi possível identificar o usuário do cofre")
        result = subprocess.run(
            ["icacls", str(self.key_path), "/inheritance:r", "/grant:r", f"{username}:(F)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Não foi possível restringir a chave do cofre ao usuário atual")

    def _fernet(self) -> Fernet:
        if not self.key_path.is_file():
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.key_path.with_suffix(".key.tmp")
            temporary.write_bytes(Fernet.generate_key())
            temporary.replace(self.key_path)
            self._restrict_key()
        return Fernet(self.key_path.read_bytes())

    def _encrypt(self, clear: bytes) -> dict[str, str | int]:
        if os.name == "nt":
            try:
                payload = self._crypt_dpapi(clear, True)
                return {"version": 2, "provider": "dpapi", "payload": base64.b64encode(payload).decode("ascii")}
            except RuntimeError:
                pass
        payload = self._fernet().encrypt(clear)
        return {"version": 2, "provider": "fernet-acl", "payload": payload.decode("ascii")}

    def _decrypt(self, envelope: dict[str, Any]) -> bytes:
        provider = envelope.get("provider")
        payload = envelope.get("payload")
        if not isinstance(payload, str):
            raise RuntimeError("O cofre local está corrompido")
        if provider == "dpapi":
            return self._crypt_dpapi(base64.b64decode(payload, validate=True), False)
        if provider == "fernet-acl":
            return self._fernet().decrypt(payload.encode("ascii"))
        raise RuntimeError("O formato do cofre local não é reconhecido")

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
            value = json.loads(self._decrypt(envelope).decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, InvalidToken, json.JSONDecodeError):
            raise RuntimeError("O cofre local está corrompido ou pertence a outro usuário")

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        clear = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        payload = json.dumps(self._encrypt(clear), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(self.path)

    def get(self, key: str) -> Any:
        with self.lock:
            return self._read().get(key)

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            data = self._read()
            data[key] = value
            self._write(data)

    def pop(self, key: str) -> Any:
        with self.lock:
            data = self._read()
            value = data.pop(key, None)
            self._write(data)
            return value

    def contains(self, key: str) -> bool:
        with self.lock:
            return key in self._read()

    def status(self) -> dict[str, Any]:
        provider = "ready"
        if self.path.is_file():
            try:
                envelope = json.loads(self.path.read_text(encoding="utf-8"))
                provider = {"dpapi": "Windows DPAPI", "fernet-acl": "Fernet + ACL local"}.get(
                    envelope.get("provider"), "unknown"
                )
            except (OSError, json.JSONDecodeError):
                provider = "unreadable"
        return {"available": self.available, "provider": provider, "stored": self.path.is_file()}
