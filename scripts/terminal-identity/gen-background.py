import sys, math
from PIL import Image
accent, base, out = sys.argv[1], sys.argv[2], sys.argv[3]
CORE  = float(sys.argv[4]) if len(sys.argv) > 4 else 0.07
LTOP  = float(sys.argv[5]) if len(sys.argv) > 5 else 0.66
LRIGHT= float(sys.argv[6]) if len(sys.argv) > 6 else 1.00
h2 = lambda s: tuple(int(s.lstrip('#')[i:i+2],16) for i in (0,2,4))
A, B = h2(accent), h2(base)
def smoothstep(e0,e1,x):
    t=min(1.,max(0.,(x-e0)/(e1-e0))); return t*t*(3-2*t)
W = H = 500
w_far = 1.0/(1.0+(1.0/CORE)**2)
img=Image.new('RGB',(W,H)); px=img.load()
for y in range(H):
    v=y/(H-1)
    tv=1.0-smoothstep(0.0,LRIGHT,v)
    for x in range(W):
        u=1-x/(W-1)
        w=1.0/(1.0+(math.sqrt(u*v)/CORE)**2)
        w=max(0.0,(w-w_far)/(1.0-w_far))
        w *= (1.0-smoothstep(0.0,LTOP,u))*tv        # product: smooth everywhere
        px[x,y]=tuple(round(A[i]*w+B[i]*(1-w)) for i in range(3))
img.save(out)
