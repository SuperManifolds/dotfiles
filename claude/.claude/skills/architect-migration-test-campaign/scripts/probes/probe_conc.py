import socket,threading,time,sys
# N concurrent redis connections held across a migration; reports total resets.
# args: host port [conns] [seconds]
H=sys.argv[1]; P=int(sys.argv[2]); CONNS=int(sys.argv[3]) if len(sys.argv)>3 else 20; DUR=float(sys.argv[4]) if len(sys.argv)>4 else 60
resets=[0]; lock=threading.Lock(); stop=[False]
def worker():
    def c():
        try:
            s=socket.create_connection((H,P),3); s.settimeout(2); return s
        except Exception:
            return None
    s=c()
    while s is None and not stop[0]: s=c()
    while not stop[0]:
        try:
            s.sendall(b'PING\r\n'); d=s.recv(64)
            if not d: raise ConnectionError()
        except Exception:
            with lock: resets[0]+=1
            s=c()
        time.sleep(0.05)
ts=[threading.Thread(target=worker) for _ in range(CONNS)]
[t.start() for t in ts]; time.sleep(DUR); stop[0]=True; [t.join(2) for t in ts]
print('RESULT conns=%d total_resets=%d'%(CONNS,resets[0]))
