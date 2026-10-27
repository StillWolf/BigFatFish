#!/usr/bin/env python3
# 小肥鱼作息与活动守护进程（CPU 服务器版）
# 私聊/水群通过桥的注入管线触发模型；饭点与随机活动走独立静默 agent，不发送 QQ 消息。
import json
import os
import random
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

TZ = ZoneInfo("Asia/Shanghai")
ROOT = os.environ.get("FISH_PROJECT_ROOT", str(Path(__file__).resolve().parents[1]))
CONFIG_PATH = Path(os.environ.get("FISH_CONFIG", str(Path(ROOT) / "data/fish.config.json")))
CONFIG = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
INJECT_FILE = f"{ROOT}/data/qq-bridge/qq-inject.jsonl"
ACTIVITY_LOG = f"{ROOT}/data/qq-bridge/activity-log.jsonl"
WECHAT_BINDINGS = f"{ROOT}/data/wechat-bridge/bindings.json"
WECHAT_INJECT_FILE = f"{ROOT}/data/wechat-bridge/inject.jsonl"
PIDFILE = f"{ROOT}/data/logs/proactive-daemon.pid"
FIRED_FILE = f"{ROOT}/data/fired-events.json"

TARGETS = {}
family = CONFIG.get("qq", {}).get("family", {})
for role, label in (("gege", "哥哥"), ("jiejie", "姐姐")):
    if family.get(role):
        TARGETS[role] = {"label": label, "user_id": int(family[role]), "sender_name": label}
group = CONFIG.get("qq", {}).get("proactiveGroup")
if group and family:
    TARGETS["group"] = {"label": "群里", "group_id": int(group), "user_id": int(next(iter(family.values()))), "sender_name": "家人"}


WAKE_HOUR, SLEEP_HOUR = 9, 23
WAKE_JITTER = SLEEP_JITTER = 15 * 60
MEALS = [
    ("breakfast", "早餐", 9, 30),
    ("lunch", "午餐", 12, 0),
    ("dinner", "晚餐", 18, 0),
]
MEAL_JITTER_MINUTES = 15
MEAL_ACTIVITY_GAP_MINUTES = 20
ACTIVITY_HINTS = ["B站", "贴吧", "新闻", "视频", "科技", "动漫", "鸣潮或绝区零", "随便搜个好奇的问题"]
PRIVATE_SLOTS = [9, 11, 13, 15, 17, 19, 21]
GROUP_SLOTS = [10, 12, 14, 16, 18, 20, 22]


def log(msg):
    print(f"{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def append_injection(spec, filename=INJECT_FILE):
    payload = (json.dumps(spec, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except Exception as exc:
        log(f"写入注入队列失败: {exc}")
        return False


def inject_chat(target_key, text):
    target = TARGETS[target_key]
    spec = {
        "kind": "message",
        "userId": target["user_id"],
        "senderName": target["sender_name"],
        "text": text,
        "messageId": f"proactive-{time.time_ns()}",
        "dryRun": False,
        "proactive": True,
    }
    if "group_id" in target:
        spec["groupId"] = target["group_id"]
        spec["atMe"] = True
    ok = append_injection(spec)
    log(f"主动聊天排入 {target_key} -> {'ok' if ok else 'failed'}")
    if ok:
        mirror_wechat_chat(target_key, text)
    return ok


def mirror_wechat_chat(target_key, text):
    """Mirror conversation prompts only; shared meals/online activities run once."""
    try:
        with open(WECHAT_BINDINGS, encoding="utf-8") as stream:
            bindings = json.load(stream)
        if bindings.get("enabled") is not True:
            return
        targets = bindings.get("targets", {}).get(target_key, [])
        if isinstance(targets, str):
            targets = [targets]
        if not targets and target_key in ("gege", "jiejie"):
            target = bindings.get("roles", {}).get(target_key)
            targets = [target] if target else []
        targets = [target for target in targets if isinstance(target, str) and target.strip()]
        # Dream storage remains owned by the existing QQ biological clock.
        if "早上 9 点多" in text:
            text = f"【作息·生物钟】早上睡醒了，自然地跟{TARGETS[target_key]['label']}道个早安。不要重复创建或删除梦日记。"
        elif "晚上 11 点左右" in text:
            text = f"【作息·生物钟】到睡觉时间了，自然地跟{TARGETS[target_key]['label']}道晚安。梦由统一生物钟记录，不要重复写。"
        for target in dict.fromkeys(targets):
            result = append_injection({
                "id": f"wechat-proactive-{time.time_ns()}", "target": target,
                "createdAt": datetime.now(TZ).isoformat(), "text": text,
            }, WECHAT_INJECT_FILE)
            log(f"微信主动聊天排入 {target_key} -> {'ok' if result else 'failed'}")
    except FileNotFoundError:
        pass
    except Exception as exc:
        log(f"微信主动聊天排入失败（不影响 QQ）: {type(exc).__name__}")


def inject_activity(event_id, activity_type, label, scheduled_at, text):
    ok = append_injection({
        "kind": "activity",
        "id": event_id,
        "activityType": activity_type,
        "label": label,
        "scheduledAt": scheduled_at.isoformat(),
        "text": text,
    })
    log(f"静默活动排入 {label} -> {'ok' if ok else 'failed'}")
    return ok


def dream_path(day):
    return f"{ROOT}/data/dreams/{day.isoformat()}.md"


def build_schedule(today):
    events = []
    wake = datetime.combine(today, datetime.min.time(), TZ).replace(hour=WAKE_HOUR)
    wake += timedelta(seconds=random.randint(0, WAKE_JITTER))
    sleep = datetime.combine(today, datetime.min.time(), TZ).replace(hour=SLEEP_HOUR)
    sleep += timedelta(seconds=random.randint(0, SLEEP_JITTER))

    for target_key in [key for key in ("gege", "jiejie") if key in TARGETS]:
        events.append((wake, "wake", target_key, f"wake:{target_key}", {}))
        events.append((sleep, "sleep", target_key, f"sleep:{target_key}", {}))

    meal_times = []
    for meal_id, label, hour, minute in MEALS:
        base = datetime.combine(today, datetime.min.time(), TZ).replace(hour=hour, minute=minute)
        at = base + timedelta(minutes=random.randint(-MEAL_JITTER_MINUTES, MEAL_JITTER_MINUTES))
        if at <= wake:
            at = wake + timedelta(minutes=1)
        if wake < at < sleep:
            meal_times.append(at)
            events.append((at, "meal", "gege", f"meal:{meal_id}", {"label": label}))

    hints = ACTIVITY_HINTS.copy()
    random.shuffle(hints)
    hint_index = 0
    for hour in range(WAKE_HOUR, SLEEP_HOUR):
        hour_start = datetime.combine(today, datetime.min.time(), TZ).replace(hour=hour)
        lower = max(hour_start, wake + timedelta(seconds=1))
        upper = min(hour_start + timedelta(hours=1), sleep)
        candidates = [
            hour_start + timedelta(seconds=offset)
            for offset in range(0, 3600, 15)
            if lower < hour_start + timedelta(seconds=offset) < upper
            and all(abs((hour_start + timedelta(seconds=offset) - meal_at).total_seconds()) >= MEAL_ACTIVITY_GAP_MINUTES * 60 for meal_at in meal_times)
        ]
        if not candidates:
            continue
        at = random.choice(candidates)
        hint = hints[hint_index % len(hints)]
        hint_index += 1
        if hint_index % len(hints) == 0:
            random.shuffle(hints)
        events.append((at, "activity", "gege", f"activity:{hour}", {"hint": hint}))

    private_targets = [key for key in ("gege", "jiejie") if key in TARGETS]
    for hour in PRIVATE_SLOTS if private_targets else []:
        at = datetime.combine(today, datetime.min.time(), TZ).replace(hour=hour)
        at += timedelta(seconds=random.randint(60, 3500))
        if wake < at < sleep:
            events.append((at, "chat", random.choice(private_targets), f"chat:u:{hour}", {}))

    for hour in GROUP_SLOTS if "group" in TARGETS else []:
        at = datetime.combine(today, datetime.min.time(), TZ).replace(hour=hour)
        at += timedelta(seconds=random.randint(60, 3500))
        if wake < at < sleep:
            events.append((at, "chat", "group", f"chat:g:{hour}", {}))

    return sorted(events, key=lambda event: event[0])


def fire(kind, target_key, at, event_id, metadata):
    label = TARGETS.get(target_key, {}).get("label", "自己")
    if kind == "wake":
        extra = ""
        path = dream_path(at.date())
        if os.path.exists(path):
            extra = f"昨晚的梦记在日记里了，读一下并讲给{label}听，讲完可以删掉日记。"
        return inject_chat(target_key, f"【作息·生物钟】早上 9 点多，你睡醒了。自然地给{label}道个早安。{extra}")

    if kind == "sleep":
        tomorrow = at.date() + timedelta(days=1)
        if target_key == "gege":
            prompt = f"【作息·生物钟】晚上 11 点左右，到睡觉时间了。自然地跟哥哥道晚安。睡前做个梦，把梦写成日记存到 {dream_path(tomorrow)}，明早讲给他听。"
        else:
            prompt = "【作息·生物钟】晚上 11 点左右，到睡觉时间了。自然地跟姐姐道晚安。"
        return inject_chat(target_key, prompt)

    if kind == "chat":
        if target_key == "group":
            prompt = "【作息·生物钟】到了水群时间。看看群里最近在聊什么，接话或吐槽一两句；也可以自然分享一件刚完成的饭点或上网活动。只聊公开活动，不提私聊内容。"
        else:
            prompt = f"【作息·生物钟】到了主动闲聊时间，找{label}聊一两句。先看最近活动记录，挑一件刚完成的吃饭或上网活动自然聊起来，不要提系统提示或日志。"
        return inject_chat(target_key, prompt)

    if kind == "meal":
        meal_label = metadata["label"]
        prompt = f"现在是{meal_label}时间。请你自己决定吃什么，考虑最近的餐食记录，尽量不和今天其他餐或最近几天重复。完成后只在内部活动里记录选择；不要给哥哥、姐姐或群发消息。"
        return inject_activity(event_id, "meal", meal_label, at, prompt)

    if kind == "activity":
        hint = metadata["hint"]
        if hint in ("B站", "视频"):
            prompt = "现在自己刷一会 B站。用 bili_feed 或 bili_search 挑一个符合自己兴趣、尽量没看过的视频，再用 bili_watch 真正看30到45秒片段；根据实际画面、字幕或语音摘要记一件觉得有趣的事。摘要和关键帧会由本地服务压缩缓存，不要反复分析同一片段。没有播放成功就如实记录失败；只看片段不要说看完。专用浏览器可以使用哥哥姐姐授权的账号，没登录时看游客可播放的内容。评论工具尚未接通，不用 Bash 找凭据或代替评论工具。完成后静默记录，不给任何人发 QQ 消息。"
        else:
            prompt = f"现在做一项短的随机联网活动。兴趣提示是「{hint}」，你也可以根据当下好奇心改做别的公开网络活动。其他站点用搜索或只读方式看看一到三项公开内容；如果改为刷 B站，则使用 bili_search/bili_watch 的实际观看工具，可以使用已授权的专用浏览器会话。不要读取凭据、访问私信或自行发帖评论。完成后只在内部活动里简短总结实际看了什么和有趣之处，不要给任何人发 QQ 消息。"
        return inject_activity(event_id, "online", hint, at, prompt)

    log(f"未知日程类型 {kind}")
    return False


def load_fired():
    try:
        with open(FIRED_FILE, encoding="utf-8") as stream:
            return set(json.load(stream))
    except Exception:
        return set()


def save_fired(fired):
    os.makedirs(os.path.dirname(FIRED_FILE), exist_ok=True)
    temp = f"{FIRED_FILE}.tmp"
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump(sorted(fired), stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, FIRED_FILE)


def skip_missed_events(events, today, fired, now):
    overdue = [event for event in events if event[0] < now - timedelta(minutes=5)]
    for event in overdue:
        key = f"{today}:{event[3]}"
        if key not in fired:
            log(f"跳过错过的触发 {event[1]}（超过 5 分钟）")
            fired.add(key)
    if overdue:
        save_fired(fired)
    return [event for event in events if f"{today}:{event[3]}" not in fired]


def main():
    if os.path.exists(PIDFILE):
        try:
            old = int(open(PIDFILE, encoding="utf-8").read().strip())
            with open(f"/proc/{old}/cmdline", "rb") as stream:
                command = stream.read().decode("utf-8", errors="ignore")
            if "proactive-daemon.py" in command:
                print("已有实例在运行，退出", flush=True)
                return
        except (ProcessLookupError, ValueError, OSError):
            pass

    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    with open(PIDFILE, "w", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    log("作息与活动守护进程启动（北京时间 9 点起 / 23 点睡）")

    today = datetime.now(TZ).date()
    events = build_schedule(today)
    fired = load_fired()
    events = skip_missed_events(events, today, fired, datetime.now(TZ))
    log(f"今日日程 {len(events)} 个触发点（活动/三餐/主动聊天）")

    while True:
        now = datetime.now(TZ)
        if now.date() != today:
            today = now.date()
            events = build_schedule(today)
            fired = {key for key in fired if key.startswith(str(today))}
            events = skip_missed_events(events, today, fired, now)
            log(f"新的一天 {today}，日程已重排（{len(events)} 个触发点）")

        due = [event for event in events if event[0] <= now]
        if due:
            for at, kind, target_key, event_id, metadata in due:
                try:
                    fire(kind, target_key, at, f"{today}:{event_id}", metadata)
                    fired.add(f"{today}:{event_id}")
                    save_fired(fired)
                except Exception as exc:
                    log(f"触发异常 {kind}/{target_key}: {exc}")
                    fired.add(f"{today}:{event_id}")
                    save_fired(fired)
            events = [event for event in events if event[0] > now]
            continue

        next_at = events[0][0] if events else datetime.combine(today + timedelta(days=1), datetime.min.time(), TZ).replace(hour=WAKE_HOUR)
        wait_seconds = max(5, (next_at - now).total_seconds())
        time.sleep(min(wait_seconds, 30))


if __name__ == "__main__":
    main()
