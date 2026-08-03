import socket,time,sys
# Redis INCR on a held connection — proves same-socket + monotonic state continuity.
# args: host port [ticks]
H=sys.argv[1]; P=int(sys.argv[2]); N=int(sys.argv[3]) if len(sys.argv)>3 else 300
def conn():
    try:
        s=socket.create_connection((H,P),3); s.settimeout(2); return s
    except Exception:
        return None
s=conn()
while s is None: s=conn()
last=0; resets=0; regress=0; n=0
for i in range(N):
    try:
        s.sendall(b'INCR ctr\r\n'); d=s.recv(64).decode()
        v=int(d.strip().lstrip(':'))
        if v<last: regress+=1
        last=v; n+=1
    except Exception:
        resets+=1; s=conn()
        while s is None: s=conn()
    time.sleep(0.1)
print('RESULT final_ctr=%d increments=%d resets=%d regressions=%d'%(last,n,resets,regress))
