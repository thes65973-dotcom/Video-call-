import time
from collections import defaultdict
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = "badal-do-isko"
socketio = SocketIO(app, cors_allowed_origins="*")

waiting = []            # इंतज़ार करने वाले यूज़र (sid)
partner = {}            # sid -> जोड़ीदार का sid
blocked = defaultdict(set)   # sid -> जिन्हें इसने ब्लॉक किया
reports = defaultdict(int)   # ip -> रिपोर्ट की गिनती
banned_until = {}       # ip -> बैन ख़त्म होने का समय
BAN_AFTER = 3           # इतनी रिपोर्ट पर बैन
BAN_SECONDS = 24 * 3600
ip_of = {}

def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)

def is_banned(ip):
    return banned_until.get(ip, 0) > time.time()

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect")
def on_connect():
    ip_of[request.sid] = client_ip()
    if is_banned(ip_of[request.sid]):
        emit("banned")

def unlink(sid, notify=True):
    other = partner.pop(sid, None)
    if other:
        partner.pop(other, None)
        if notify:
            socketio.emit("partner_left", to=other)
    if sid in waiting:
        waiting.remove(sid)

@socketio.on("find")
def find():
    sid = request.sid
    if is_banned(ip_of.get(sid, "")):
        emit("banned")
        return
    unlink(sid)
    for other in list(waiting):
        if other != sid and other not in blocked[sid] and sid not in blocked[other]:
            waiting.remove(other)
            partner[sid] = other
            partner[other] = sid
            emit("matched", {"initiator": True})
            socketio.emit("matched", {"initiator": False}, to=other)
            return
    waiting.append(sid)
    emit("waiting")

@socketio.on("signal")
def signal(data):
    other = partner.get(request.sid)
    if other:
        socketio.emit("signal", data, to=other)

@socketio.on("chat")
def chat(text):
    other = partner.get(request.sid)
    if other and isinstance(text, str):
        socketio.emit("chat", text[:500], to=other)

@socketio.on("next")
def next_user():
    unlink(request.sid)
    emit("stopped")

@socketio.on("block")
def block():
    sid = request.sid
    other = partner.get(sid)
    if other:
        blocked[sid].add(other)
        blocked[other].add(sid)
    unlink(sid)
    emit("stopped")

@socketio.on("report")
def report():
    sid = request.sid
    other = partner.get(sid)
    if other:
        ip = ip_of.get(other, "")
        reports[ip] += 1
        if reports[ip] >= BAN_AFTER:
            banned_until[ip] = time.time() + BAN_SECONDS
            socketio.emit("banned", to=other)
        blocked[sid].add(other)
        blocked[other].add(sid)
    unlink(sid)
    emit("stopped")

@socketio.on("disconnect")
def on_disconnect():
    unlink(request.sid)
    ip_of.pop(request.sid, None)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)
