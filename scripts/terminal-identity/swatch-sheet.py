import sys, hashlib, math
sys.path.insert(0,'.')
from mint2 import oklch_to_srgb, max_chroma

def mint(repo, branch, hue_arc=None, L_RANGE=(0.22,0.38), CFRAC=(0.62,0.98)):
    d=hashlib.sha256(f'{repo}\0{branch}'.encode()).digest()
    hf=int.from_bytes(d[0:4],'big')/2**32
    cf=int.from_bytes(d[8:12],'big')/2**32
    lf=int.from_bytes(d[16:20],'big')/2**32
    if hue_arc:                       # per-project constraint, wraps past 360
        start,end=hue_arc; span=(end-start)%360 or 360
        H=(start+hf*span)%360
    else:
        H=hf*360
    L=L_RANGE[0]+lf*(L_RANGE[1]-L_RANGE[0])
    C=max_chroma(L,H)*(CFRAC[0]+cf*(CFRAC[1]-CFRAC[0]))
    rgb=[max(0.,min(1.,v)) for v in oklch_to_srgb(L,C,H)]
    r,g,b=[round(v*255) for v in rgb]
    return '#{:02x}{:02x}{:02x}'.format(r,g,b),(r*299+g*587+b*114)/1000

branches=[b for b in open('branches.txt').read().split()][:10]
def col(title, sub, arc, L, C):
    out=[f'<section><h2>{title}</h2><p class=sub>{sub}</p>']
    for b in branches:
        hexv,y=mint('weasel',b,arc,L,C)
        out.append(f'<div class=row><span class=sw style="background:{hexv}"><code>{b}</code></span>'
                   f'<span class=meta>{hexv} &nbsp; yiq {y:.0f}</span></div>')
    return ''.join(out)+'</section>'

html=('<!doctype html><meta charset=utf-8><title>branch color minting</title><style>'
'body{background:#0b0b0d;color:#d8d8de;font:14px/1.5 system-ui;margin:0;padding:32px}'
'h1{font-size:15px;letter-spacing:.09em;text-transform:uppercase;color:#8a8a94;margin:0 0 24px}'
'.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:32px}'
'h2{font-size:14px;margin:0 0 2px}.sub{color:#7c7c86;font-size:12px;margin:0 0 14px}'
'.row{display:flex;align-items:center;gap:12px;margin-bottom:7px}'
'.sw{flex:1;padding:11px 13px;border-radius:6px;border:1px solid #ffffff14}'
'.sw code{color:#fff;font:12px ui-monospace,Menlo,monospace}'
'.meta{color:#70707a;font:11px ui-monospace,Menlo,monospace;white-space:nowrap}'
'</style><h1>branch colors — minted from sha256(repo\\0branch) in OKLCH</h1><div class=cols>'
+ col('Default policy','full hue wheel · L 0.22–0.38 · C 62–98% of gamut max',None,(0.22,0.38),(0.62,0.98))
+ col('weasel family policy','hue constrained to 330–60° around its #470013 base',(330,60),(0.20,0.34),(0.70,1.0))
+ '</div>')
open('swatches.html','w').write(html)
print('ok')
