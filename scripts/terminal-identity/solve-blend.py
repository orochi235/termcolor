import colorsys, sys
h2=lambda s: tuple(int(s.lstrip('#')[i:i+2],16) for i in (0,2,4))
bg=h2(sys.argv[2]); target=h2(sys.argv[1]); blend=float(sys.argv[3]) if len(sys.argv)>3 else 0.5
th=colorsys.rgb_to_hsv(*[c/255 for c in target])[0]*360
best=None
for i in range(7200):
    h=i/20
    a=[round(c*255) for c in colorsys.hsv_to_rgb(h/360,1,1)]
    r=[blend*a[j]+(1-blend)*bg[j] for j in range(3)]
    rh,rs,rv=colorsys.rgb_to_hsv(*[c/255 for c in r])
    err=abs((rh*360)-th)
    if best is None or err<best[0]: best=(err,h,a,r,rs,rv)
err,h,a,r,rs,rv=best
print('author  #{:02x}{:02x}{:02x}  (hue {:.0f}deg)'.format(*a,h))
print('renders #{:02x}{:02x}{:02x}  hue {:.0f}deg  sat {:.0f}%  val {:.0f}%'.format(
    *[round(c) for c in r], colorsys.rgb_to_hsv(*[c/255 for c in r])[0]*360, rs*100, rv*100))
print('target  hue {:.0f}deg'.format(th))
