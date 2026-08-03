import http.client,time,sys
# Keep-alive HTTP GET loop, tolerant of one reconnect. args: host port [ticks]
H=sys.argv[1]; P=int(sys.argv[2]); N=int(sys.argv[3]) if len(sys.argv)>3 else 200
def mk(): return http.client.HTTPConnection(H,P,timeout=3)
c=mk(); ok=err=0
for i in range(N):
    try:
        c.request('GET','/'); r=c.getresponse(); r.read()
        print('OK',flush=True); ok+=1
    except Exception:
        print('ERR',flush=True); err+=1
        try: c.close()
        except Exception: pass
        c=mk()
    time.sleep(0.2)
print('RESULT ok=%d err=%d'%(ok,err))
