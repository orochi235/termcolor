import hashlib, math, sys

def oklch_to_srgb(L,C,Hdeg):
    h=math.radians(Hdeg); a=C*math.cos(h); b=C*math.sin(h)
    l_=L+0.3963377774*a+0.2158037573*b; m_=L-0.1055613458*a-0.0638541728*b; s_=L-0.0894841775*a-1.2914855480*b
    l,m,s=l_**3,m_**3,s_**3
    r=+4.0767416621*l-3.3077115913*m+0.2309699292*s
    g=-1.2684380046*l+2.6097574011*m-0.3413193965*s
    bl=-0.0041960863*l-0.7034186147*m+1.7076147010*s
    def gam(x): return 12.92*x if x<=0.0031308 else 1.055*(x**(1/2.4))-0.055
    return [gam(v) for v in (r,g,bl)]

def fits(rgb): return all(-1e-4<=v<=1+1e-4 for v in rgb)

def max_chroma(L,H):
    lo,hi=0.0,0.5
    for _ in range(40):
        mid=(lo+hi)/2
        if fits(oklch_to_srgb(L,mid,H)): lo=mid
        else: hi=mid
    return lo

def mint(repo, branch, L_RANGE=(0.22,0.38), CFRAC=(0.62,0.98)):
    d=hashlib.sha256(f'{repo}\0{branch}'.encode()).digest()
    H  = int.from_bytes(d[0:4],'big')/2**32*360
    cf = int.from_bytes(d[8:12],'big')/2**32
    lf = int.from_bytes(d[16:20],'big')/2**32
    L  = L_RANGE[0]+lf*(L_RANGE[1]-L_RANGE[0])
    # chroma as a fraction of what this (L,H) can actually hold -> even vividness
    C  = max_chroma(L,H)*(CFRAC[0]+cf*(CFRAC[1]-CFRAC[0]))
    rgb=[max(0.,min(1.,v)) for v in oklch_to_srgb(L,C,H)]
    r,g,b=[round(v*255) for v in rgb]
    return '#{:02x}{:02x}{:02x}'.format(r,g,b),H,C,L,(r*299+g*587+b*114)/1000
