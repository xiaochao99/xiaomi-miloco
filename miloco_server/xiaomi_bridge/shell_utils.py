from __future__ import annotations

import json


def shell_single_quote(s: str) -> str:
    """
    Wrap `s` as a single-quoted shell string, escaping inner single quotes.

    Rule: ' -> '\''  (close quote, escape, reopen)
    """
    return "'" + (s or "").replace("'", "'\\''") + "'"


def build_mibrain_tts_script(text: str, save: int = 0) -> str:
    """
    Build the exact ubus command used by open-xiaoai/open-xiaoai-bridge style clients.

    Example:
      ubus call mibrain text_to_speech '<json>'
    """
    payload = json.dumps({"text": text or "你好", "save": int(save)}, ensure_ascii=False, separators=(",", ":"))
    return f"ubus call mibrain text_to_speech {shell_single_quote(payload)}"


def build_play_url_script(url: str) -> str:
    payload = json.dumps({"url": url, "type": 1}, ensure_ascii=False, separators=(",", ":"))
    return f"ubus call mediaplayer player_play_url {shell_single_quote(payload)}"


def build_interrupt_script() -> str:
    # Match open-xiaoai SpeakerManager.stop_device_audio()
    return "killall tts_play.sh miplayer 2>/dev/null; mphelper pause"


def build_wakeup_script(awake: bool = True, silent: bool = True) -> str:
    """
    Wake up / cancel wake up.
    """
    if awake:
        if silent:
            return "ubus call pnshelper event_notify '{\"src\":1,\"event\":0}'"
        return "ubus call pnshelper event_notify '{\"src\":0,\"event\":0}'"

    return (
        "ubus call pnshelper event_notify '{\"src\":3, \"event\":7}'\n"
        "sleep 0.1\n"
        "ubus call pnshelper event_notify '{\"src\":3, \"event\":8}'"
    )

