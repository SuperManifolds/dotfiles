import socket,time,sys
# Holds ONE redis connection, PINGs fast, reports the largest gap between successes
# (= client-observed stall) and reconnect count.  args: host port [seconds]
H=sys.argv[1]; P=int(sys.argv[2]); DUR=float(sys.argv[3]) if len(sys.argv)>3 else 90.0
def conn():
    try:
        s=socket.create_connection((H,P),2); s.settimeout(2); return s
    except Exception:
        return None
s=conn()
while s is None: s=conn()
last=time.monotonic(); end=last+DUR; maxgap=0.0; n=0; resets=0
while time.monotonic()<end:
    ok=False
    try:
        s.sendall(b'PING\r\n'); d=s.recv(64)
        if d: ok=True
        else: raise ConnectionError('closed')
    except Exception:
        resets+=1
        ns=conn()
        if ns is not None: s=ns
    if ok:
        now=time.monotonic(); gap=now-last; last=now
        if gap>maxgap: maxgap=gap
        n+=1
    time.sleep(0.02)
print('RESULT pings=%d maxgap_ms=%.0f resets=%d'%(n, maxgap*1000, resets))
