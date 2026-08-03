import socket,time,sys
# Holds one TCP connection, non-destructively checks liveness (MSG_PEEK) each tick;
# prints OK/ERR per tick and a RESULT line.  args: host port [ticks]
H=sys.argv[1]; P=int(sys.argv[2]); N=int(sys.argv[3]) if len(sys.argv)>3 else 300
def conn():
    try:
        s=socket.create_connection((H,P),3); s.settimeout(2); return s
    except Exception:
        return None
s=conn(); ok=err=0
for i in range(N):
    try:
        if s is None:
            s=conn(); raise ConnectionError('reconnect')
        s.setblocking(False)
        try:
            d=s.recv(1,socket.MSG_PEEK)
            if d==b'': raise ConnectionError('peer closed')
        except BlockingIOError:
            pass
        s.setblocking(True)
        print('OK',flush=True); ok+=1
    except Exception:
        print('ERR',flush=True); err+=1; s=conn()
    time.sleep(0.2)
print('RESULT ok=%d err=%d'%(ok,err))
