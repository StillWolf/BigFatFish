#!/usr/bin/env python3
"""Local status page and optional conservative process recovery."""
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from operational_health import alive, collect, port_open

PROJECT = Path(os.environ.get('FISH_PROJECT_ROOT', Path(__file__).resolve().parents[1]))
ROOT = PROJECT / 'data/health'
ALLOWED = {'dsh', 'activities', 'diary', 'bilibili', 'xiaohongshu', 'tts'}


def process_exists(fragment):
    try:
        for path in Path('/proc').iterdir():
            if not path.name.isdigit(): continue
            try:
                if fragment.encode() in (path / 'cmdline').read_bytes(): return True
            except OSError: pass
    except OSError: pass
    return False


def dsh_process_exists():
    try:
        for path in Path('/proc').iterdir():
            if not path.name.isdigit(): continue
            try:
                args = [os.fsdecode(arg) for arg in (path / 'cmdline').read_bytes().split(b'\0') if arg]
                if 'web' in args and any(Path(arg).name in ('dsh', 'dsh.js') for arg in args):
                    return True
            except OSError: pass
    except OSError: pass
    return False


class RetryController:
    def __init__(self, cooldown=300):
        self.failures, self.last = {}, {}
        self.cooldown = cooldown

    def should_restart(self, name, absent, now):
        if not absent:
            self.failures.pop(name, None); return False
        self.failures[name] = self.failures.get(name, 0) + 1
        if self.failures[name] < 2 or now - self.last.get(name, -self.cooldown) < self.cooldown:
            return False
        self.last[name] = now
        return True


def restart_command(name):
    script = PROJECT / 'scripts'
    python = os.environ.get('FISH_MONITOR_PYTHON', sys.executable)
    if name == 'dsh': return ['bash', str(script / 'start-dsh.sh')]
    if name == 'activities': return [python, str(script / 'proactive-daemon.py')]
    if name == 'diary': return [python, str(script / 'fish-diary.py'), '--daemon']
    if name == 'bilibili': return ['bash', str(script / 'start-bilibili.sh')]
    if name == 'xiaohongshu': return ['bash', str(script / 'start-xiaohongshu.sh')]
    if name == 'tts': return [os.environ.get('FISH_TTS_PYTHON', python), str(script / 'tts-server.py')]
    raise ValueError('unsupported component')


def restart_absent(name, status):
    """Only a confirmed absent process is restartable; never reset a login."""
    if name == 'dsh': return status['qq']['state'] == 'down' and not port_open(6700) and not dsh_process_exists()
    if name == 'activities': return not status['activities']['running'] and not process_exists('proactive-daemon.py')
    if name == 'diary': return not status['diary']['running'] and not process_exists('fish-diary.py')
    if name == 'bilibili':
        row=status.get('bilibili') or {}
        return not row.get('supervisorRunning') and not row.get('browserReady') and not process_exists('bilibili-runtime.py')
    if name == 'xiaohongshu':
        row=status.get('xiaohongshu') or {}
        return not row.get('supervisorRunning') and not row.get('browserReady') and not process_exists('xiaohongshu-runtime.py')
    if name == 'tts': return not status['tts']['ready'] and not process_exists('tts-server.py')
    return False


def atomic_status(value):
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700); ROOT.chmod(0o700)
    path=ROOT/'status.json'; tmp=path.with_name(path.name+'.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w',encoding='utf8') as f:
        json.dump(value,f,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)


def transition(event):
    try:
        fd=os.open(ROOT/'events.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'a',encoding='utf8') as f:f.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
    except OSError: pass


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BigFatFish 运行状态</title><style>body{font:16px system-ui;max-width:900px;margin:32px auto;padding:0 16px;color:#234}pre{white-space:pre-wrap;background:#f2f6f8;padding:16px;border-radius:8px}</style>
<h1>BigFatFish 运行状态</h1><p>这里只显示服务状态和浏览摘要用量，不显示聊天或日记内容。</p><pre id="state">正在读取...</pre>
<script>async function refresh(){try{let r=await fetch('/status',{cache:'no-store'}),s=await r.json(),q=s.qq||{},a=s.activities||{},d=s.diary||{},b=s.bilibili||{},x=s.xiaohongshu||{},u=s.usage||{};
let translate={online:'在线',offline:'掉线，可能需要重新登录',down:'未运行',stale:'状态过期',unknown:'未确认'};
let lines=['更新时间：'+(s.updatedAt?new Date(s.updatedAt*1000).toLocaleString():'尚未完成首次检查'),'QQ：'+(translate[q.state]||'未确认'),
'作息：'+(a.running?'运行中':'未运行')+'；待重试 '+(a.retryPending??0)+'，结果待核查 '+(a.uncertain??0),
'日记服务：'+(d.running?'运行中':'未运行'),'B站浏览器：'+(b.enabled?(b.browserReady?'就绪':'不可用'):'未启用'),
'B站登录：'+(b.enabled?(b.loggedIn===true?'已登录':b.loggedIn===false?'未登录':'未确认'):'未启用'),
'B站私信轮询：'+(b.socialEnabled?(b.socialMonitorHealthy===true?'正常':b.socialMonitorHealthy===false?'异常':'未确认'):'未启用'),
'小红书浏览器：'+(x.enabled?(x.browserReady?'就绪':'不可用'):'未启用'),'语音服务：'+(s.tts?.ready?'就绪':'未启用或不可用'),
'浏览摘要用量（仅统计启用后有 usage 的请求）：'];for(const [name,v] of Object.entries(u.sources||{}))lines.push(name+'：'+v.calls+' 次，'+v.total_tokens+' Token');
if(s.monitor?.state==='stale')lines.unshift('状态更新已过期，请检查监控进程。');document.getElementById('state').textContent=lines.join('\\n')}
catch(e){document.getElementById('state').textContent='状态服务暂不可用'}}refresh();setInterval(refresh,30000)</script></html>'''.encode('utf8')


def main():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700); ROOT.chmod(0o700)
    lock=(ROOT/'monitor.lock').open('w')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: return
    names=set(filter(None,os.environ.get('FISH_MONITOR_COMPONENTS','dsh,activities,diary,bilibili,xiaohongshu,tts').split(','))) & ALLOWED
    features={'bilibili':'bilibili' in names,'xiaohongshu':'xiaohongshu' in names}
    autorestart=os.environ.get('FISH_MONITOR_AUTORESTART')=='1'
    controller=RetryController();state={'updatedAt':0};previous={};guard=threading.Lock();stopping=threading.Event()

    def update():
        while not stopping.is_set():
            try:
                status=collect(PROJECT,bili_root=os.environ.get('FISH_BILIBILI_ROOT'),xhs_root=os.environ.get('FISH_XHS_ROOT'),
                               activity_pidfile=os.environ.get('FISH_ACTIVITY_PIDFILE'),features=features)
                component_states={'qq':status['qq']['state'],'activities':'running' if status['activities']['running'] else 'down',
                    'diary':'running' if status['diary']['running'] else 'down',
                    'bilibili':'ready' if status['bilibili'].get('browserReady') else 'down' if 'bilibili' in names else 'disabled',
                    'xiaohongshu':'ready' if status['xiaohongshu'].get('browserReady') else 'down' if 'xiaohongshu' in names else 'disabled',
                    'tts':'ready' if status['tts']['ready'] else 'down'}
                for name,current in component_states.items():
                    if name in previous and previous[name]!=current:
                        transition({'at':int(time.time()),'component':name,'state':current})
                    previous[name]=current
                if autorestart:
                    for name in sorted(names):
                        absent=restart_absent(name,status)
                        if controller.should_restart(name,absent,time.monotonic()):
                            try:
                                log=ROOT/('restart-'+name+'.log')
                                fd=os.open(log,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
                                with os.fdopen(fd,'ab',buffering=0) as output:
                                    subprocess.Popen(restart_command(name),cwd=PROJECT,env=os.environ.copy(),stdin=subprocess.DEVNULL,
                                                     stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                                transition({'at':int(time.time()),'component':name,'state':'restart_requested'})
                            except (OSError,ValueError):
                                transition({'at':int(time.time()),'component':name,'state':'restart_failed'})
                status['monitor']={'autoRestart':autorestart,'components':sorted(names)}
                atomic_status(status)
                with guard: state.clear();state.update(status)
            except Exception:
                transition({'at':int(time.time()),'component':'monitor','state':'check_failed'})
            stopping.wait(30)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_args): pass
        def do_GET(self):
            if self.path=='/':data=PAGE;kind='text/html; charset=utf-8'
            elif self.path=='/status':
                with guard: snapshot=json.loads(json.dumps(state))
                if not snapshot.get('updatedAt') or time.time()-snapshot['updatedAt']>120:
                    snapshot.setdefault('monitor',{})['state']='stale'
                data=json.dumps(snapshot,ensure_ascii=False).encode()
                kind='application/json; charset=utf-8'
            else:return self.send_error(404)
            self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)

    server=ThreadingHTTPServer((os.environ.get('FISH_MONITOR_BIND','127.0.0.1'),int(os.environ.get('FISH_MONITOR_PORT','18180'))),Handler)
    server.daemon_threads=True
    def stop(*_args):
        stopping.set();threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    thread=threading.Thread(target=update,daemon=True);thread.start()
    try: server.serve_forever()
    finally: stopping.set();server.server_close();thread.join(timeout=15)


if __name__=='__main__': main()
