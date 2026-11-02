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
PENDING_FILE = f"{ROOT}/data/schedule-pending.json"
QQ_RUNTIME_FILE = f"{ROOT}/data/qq-bridge/qq-runtime.json"
RETRY_WINDOW_SECONDS = 15 * 60

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
XHS_ROOT = Path(os.environ.get("FISH_XHS_ROOT", str(Path(ROOT) / "data/xiaohongshu")))
PRIVATE_SLOTS = [9, 11, 13, 15, 17, 19, 21]
GROUP_SLOTS = [10, 12, 14, 16, 18, 20, 22]


def log(msg):
    print(f"{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def append_injection(spec, filename=INJECT_FILE):
    payload = (json.dumps(spec, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    opened = False
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        opened = True
        with os.fdopen(fd, "ab") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return True
    except Exception as exc:
        log(f"写入注入队列失败: {exc}")
        # A failure after opening may have written some or all of the line.
        # Its delivery is uncertain and must not be retried automatically.
        return None if opened else False


def bridge_available(require_online=False):
    """Avoid appending work while the bridge would discard it on startup."""
    try:
        with open(QQ_RUNTIME_FILE, encoding='utf-8') as stream:
            state = json.load(stream)
        age = time.time() - float(state['updatedAt']) / 1000
        if age < -30 or age > 180 or not (state.get('injection') or {}).get('enabled'):
            return False
        os.kill(int(state['pid']), 0)
        return not require_online or state.get('botOnline') is True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def inject_chat(target_key, text, *, mirror=True):
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
    ok = append_injection(spec) if bridge_available(require_online=True) else False
    log(f"主动聊天排入 {target_key} -> {'ok' if ok else 'failed'}")
    if mirror:
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
    try:
        if os.environ.get('FISH_XHS_ENABLED') != '0' and (XHS_ROOT / 'activity-enabled').read_text().strip() == '1':
            hints.append('小红书')
    except OSError:
        pass
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
    if kind in ('meal', 'activity') and not bridge_available():
        log(f'桥暂不可用，稍后重试 {kind}')
        return False
    label = TARGETS.get(target_key, {}).get("label", "自己")
    stamp = f"（现在北京时间 {datetime.now(TZ).strftime('%m-%d %H:%M')}）"
    mirror = metadata.get('_mirrorWechat', True)
    if kind == "wake":
        extra = ""
        path = dream_path(at.date())
        if target_key == "gege" and os.path.exists(path):
            extra = f"昨晚的梦记在日记里了，读一下并讲给{label}听，讲完可以删掉日记。"
        return inject_chat(target_key, f"【作息·生物钟】早上 9 点多，你睡醒了。自然地给{label}道个早安。{extra}{stamp}", mirror=mirror)

    if kind == "sleep":
        tomorrow = at.date() + timedelta(days=1)
        if target_key == "gege":
            prompt = f"【作息·生物钟】晚上 11 点左右，到睡觉时间了。自然地跟哥哥道晚安。睡前做个梦，把梦写成日记存到 {dream_path(tomorrow)}，明早讲给他听。{stamp}"
        else:
            prompt = f"【作息·生物钟】晚上 11 点左右，到睡觉时间了。自然地跟姐姐道晚安。{stamp}"
        return inject_chat(target_key, prompt, mirror=mirror)

    if kind == "chat":
        if target_key == "group":
            prompt = f"【作息·生物钟】到了水群时间。看看群里最近在聊什么，接话或吐槽一两句；也可以自然分享一件刚完成的饭点或上网活动。只聊公开活动，不提私聊内容。{stamp}"
        else:
            prompt = f"【作息·生物钟】到了主动闲聊时间，找{label}聊一两句。先看最近活动记录，挑一件刚完成的吃饭或上网活动自然聊起来，不要提系统提示或日志。{stamp}"
        return inject_chat(target_key, prompt, mirror=mirror)

    if kind == "meal":
        meal_label = metadata["label"]
        prompt = f"现在是{meal_label}时间。请你自己决定吃什么，考虑最近的餐食记录，尽量不和今天其他餐或最近几天重复。完成后只在内部活动里记录选择；不要给哥哥、姐姐或群发消息。"
        return inject_activity(event_id, "meal", meal_label, at, prompt)

    if kind == "activity":
        hint = metadata["hint"]
        if hint == '小红书':
            prompt = '现在自己刷一会小红书。游客优先用 xhs_feed 选感兴趣且尽量没看过的笔记，用 xhs_read 实际读取，或用 xhs_watch 播放视频片段；搜索若提示登录就改看推荐。只根据真实返回的文字、画面和语音摘要简短记录见闻。标题不代表已读，缓存是之前的记录，videoPlayed=false 表示没有看过视频，看片段不等于看完全片。页面要求验证或受限时停止并如实记录。不要发QQ消息，不要发布、评论、点赞或读取凭据。'
        elif hint in ("B站", "视频"):
            prompt = "现在自己刷一会 B站。用 bili_feed 或 bili_search 挑一个符合自己兴趣、尽量没看过的视频，再用 bili_watch 真正看30到45秒片段；根据实际画面、字幕或语音摘要记一件觉得有趣的事。摘要和关键帧会由本地服务压缩缓存，不要反复分析同一片段。没有播放成功就如实记录失败；只看片段不要说看完。专用浏览器可以使用哥哥姐姐授权的账号，没登录时看游客可播放的内容。你也可以用 bili_followings 查看关注的人和他们的视频，或通过 bili_creator 和 bili_follow 关注喜欢的作者。如果你真想就看到的内容说点什么，可以先用 bili_comments 看少量评论，再按自己的想法用 bili_comment 或 bili_reply 评论；不必每次都评论。评论公开，别透露私聊、日记或凭据。你也可以在想整理自己B站资料时用专用资料和头像工具自行决定修改，但不必每次都改；公开资料不能包含私聊或日记，提交不代表审核通过。不要用 Bash 操作账号。完成后静默记录，不给任何人发 QQ 消息。"
        else:
            prompt = f"现在做一项短的随机联网活动。兴趣提示是「{hint}」，你也可以根据当下好奇心改做别的公开网络活动。其他站点用搜索或只读方式看看一到三项公开内容；如果改为刷 B站，则使用 bili_search/bili_watch 的实际观看工具，可以使用已授权的专用浏览器会话。不要读取凭据或自行发帖；B站私信只通过专用工具处理且不透露对话内容。如果选择 B站，看过视频后可以通过专用评论工具按自己的想法评论，不必每次都评论。完成后只在内部活动里简短总结实际看了什么和有趣之处，不要给任何人发 QQ 消息。"
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


def load_pending():
    try:
        with open(PENDING_FILE, encoding='utf-8') as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_pending(pending):
    path = Path(PENDING_FILE); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(pending, stream, ensure_ascii=False)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def recover_pending(events, today, fired, pending):
    """Restore original failed event times and hints after a restart."""
    restored = {}
    for key, item in pending.items():
        if not key.startswith(str(today) + ':') or key in fired or item.get('status') != 'retry':
            continue
        try:
            at = datetime.fromisoformat(item['scheduledAt'])
            if at.tzinfo is None: continue
            restored[key] = (at, item['kind'], item['target'], item['eventId'], item['metadata'])
        except (KeyError, TypeError, ValueError):
            continue
    result = [event for event in events if f'{today}:{event[3]}' not in restored]
    return sorted(result + list(restored.values()), key=lambda event: event[0])


def process_due_events(events, today, fired, pending, now, fire_event=None):
    """Retry only definitely unqueued events; never duplicate an uncertain write."""
    fire_event = fire_event or fire
    keep = []
    for event in events:
        at, kind, target, event_id, metadata = event
        key = f'{today}:{event_id}'
        if key in fired: continue
        if at > now:
            keep.append(event); continue
        item = pending.get(key) or {}
        if item.get('status') in ('uncertain', 'writing', 'queued'):
            if item.get('status') == 'writing':
                item['status'] = 'uncertain'; pending[key] = item; save_pending(pending)
                log(f'上次触发结果未知 {kind}，不自动重复')
            fired.add(key); save_fired(fired); continue
        asleep = kind == 'activity' and (now.hour < WAKE_HOUR or now.hour >= SLEEP_HOUR)
        if asleep or (now - at).total_seconds() > RETRY_WINDOW_SECONDS:
            log(f'触发已过期 {kind}，停止重试')
            fired.add(key); save_fired(fired)
            pending.pop(key, None); save_pending(pending)
            continue
        if float(item.get('nextRetryAt', 0)) > now.timestamp():
            keep.append(event); continue
        # Persist intent before writing to the shared queue. A crash during the
        # append becomes uncertain rather than silently producing a duplicate.
        mirror_once = kind in ('wake', 'sleep', 'chat') and not item.get('wechatMirrored', False)
        pending[key] = {'status': 'writing', 'scheduledAt': at.isoformat(), 'kind': kind,
                        'target': target, 'eventId': event_id, 'metadata': metadata,
                        'attempts': int(item.get('attempts', 0)),
                        'wechatMirrored': bool(item.get('wechatMirrored', False) or mirror_once)}
        save_pending(pending)
        try:
            result = fire_event(kind, target, at, key, {**metadata, '_mirrorWechat': mirror_once})
        except Exception as exc:
            log(f'触发结果未知 {kind}: {type(exc).__name__}')
            result = None
        if result is False:
            attempts = int(item.get('attempts', 0)) + 1
            delay = min(300, 30 * 2 ** min(attempts - 1, 4))
            pending[key] = {'status': 'retry', 'scheduledAt': at.isoformat(), 'kind': kind,
                            'target': target, 'eventId': event_id, 'metadata': metadata,
                            'attempts': attempts, 'nextRetryAt': now.timestamp() + delay,
                            'wechatMirrored': bool(item.get('wechatMirrored', False) or mirror_once)}
            save_pending(pending); keep.append(event)
            continue
        if result is None:
            pending[key]['status'] = 'uncertain'
            save_pending(pending)
            log(f'触发结果未知 {kind}，保留记录且不自动重复')
        else:
            pending[key]['status'] = 'queued'; save_pending(pending)
        fired.add(key); save_fired(fired)
        if result is not None:
            pending.pop(key, None); save_pending(pending)
    return keep


def skip_missed_events(events, today, fired, now, pending=None):
    pending = pending or {}
    overdue = [event for event in events if event[0] < now - timedelta(minutes=5)
               and (pending.get(f'{today}:{event[3]}') or {}).get('status') != 'retry']
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
    pending = load_pending()
    events = recover_pending(events, today, fired, pending)
    events = skip_missed_events(events, today, fired, datetime.now(TZ), pending)
    log(f"今日日程 {len(events)} 个触发点（活动/三餐/主动聊天）")

    while True:
        now = datetime.now(TZ)
        if now.date() != today:
            today = now.date()
            events = build_schedule(today)
            fired = {key for key in fired if key.startswith(str(today))}
            pending = {key: value for key, value in pending.items() if key.startswith(str(today)) or value.get('status') in ('uncertain', 'writing')}
            save_pending(pending)
            events = recover_pending(events, today, fired, pending)
            events = skip_missed_events(events, today, fired, now, pending)
            log(f"新的一天 {today}，日程已重排（{len(events)} 个触发点）")

        if any(event[0] <= now for event in events):
            events = process_due_events(events, today, fired, pending, now)

        if events:
            def eligible_at(event):
                retry = (pending.get(f'{today}:{event[3]}') or {}).get('nextRetryAt', 0)
                return max(event[0], datetime.fromtimestamp(float(retry), TZ)) if retry else event[0]
            next_at = min(eligible_at(event) for event in events)
        else:
            next_at = datetime.combine(today + timedelta(days=1), datetime.min.time(), TZ).replace(hour=WAKE_HOUR)
        wait_seconds = max(5, (next_at - now).total_seconds())
        time.sleep(min(wait_seconds, 30))


if __name__ == "__main__":
    main()
