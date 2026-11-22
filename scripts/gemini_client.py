#!/usr/bin/env python3
"""
Google Gemini API & Profile Configuration Loader for the Job Hunt Swarm.
Uses zero external dependencies by default (standard library urllib.request),
while supporting PyYAML if installed.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
PROFILE_PATH = ROOT_DIR / "profile" / "candidate_profile.yaml"
RESUME_PATH = ROOT_DIR / "profile" / "base_resume.md"


def load_dotenv() -> None:
    for candidate_env in (ENV_PATH, ROOT_DIR / ".env.example"):
        if not candidate_env.exists():
            continue
        for line in candidate_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _simple_yaml_parse(text: str) -> Dict[str, Any]:
    """Lightweight parser for candidate_profile.yaml when PyYAML is not installed."""
    result: Dict[str, Any] = {}
    current_section: Optional[str] = None
    current_list_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            current_section = stripped[:-1].strip()
            result[current_section] = {}
            current_list_key = None
        elif indent == 2 and current_section is not None:
            if stripped.startswith("- "):
                if isinstance(result[current_section], dict) and not result[current_section]:
                    result[current_section] = []
                if isinstance(result[current_section], list):
                    result[current_section].append(stripped[2:].strip().strip('"').strip("'"))
            elif ":" in stripped:
                k, v = stripped.split(":", 1)
                k = k.strip()
                v = v.strip()
                if not v:
                    result[current_section][k] = []
                    current_list_key = k
                elif v == "[]":
                    result[current_section][k] = []
                    current_list_key = None
                elif v.lower() in ("true", "false"):
                    result[current_section][k] = v.lower() == "true"
                    current_list_key = None
                elif v.isdigit():
                    result[current_section][k] = int(v)
                    current_list_key = None
                else:
                    result[current_section][k] = v.strip('"').strip("'")
                    current_list_key = None
        elif indent >= 4 and current_section is not None and current_list_key is not None:
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                result[current_section][current_list_key].append(val)

    return result


def load_profile() -> Dict[str, Any]:
    if not PROFILE_PATH.exists():
        return {}
    text = PROFILE_PATH.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return _simple_yaml_parse(text)


def load_base_resume() -> str:
    if not RESUME_PATH.exists():
        return ""
    return RESUME_PATH.read_text(encoding="utf-8")


def call_gemini(
    prompt: str,
    model: str = "gemini-2.5-flash",
    system_instruction: str = "",
    json_output: bool = False,
    temperature: float = 0.2,
) -> Optional[str]:
    """Calls Google Gemini REST API using GEMINI_API_KEY."""
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    if json_output:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError):
        return None
    return None


def extract_json(text: str) -> Dict[str, Any]:
    """Extracts JSON object from plain text or markdown code blocks."""
    if not text:
        return {}
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}
