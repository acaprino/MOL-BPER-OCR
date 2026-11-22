"""How many reject prototypes, and split how? Measured, not assumed.

Without a reject class the classifier *must* pick a page: 100% of negatives were
assigned to one, by construction rather than by error. One averaged reject prototype
takes that to 44%, which is better and still bad.

The suspicion this script tests is that averaging a heterogeneous category (document
management, another application, blank transitions) yields a centroid resembling none
of them. It does. Splitting by the three types already distinguished during labelling
takes false positives to 20% at no cost in page accuracy, while k-means over the same
negatives buys a few more points of rejection and pays 10 to 50 points of accuracy:
the more reject prototypes exist, the likelier one of them resembles a real page by
accident.

Result table and interpretation: docs/adr/0008.

    python tools/measure_reject_prototypes.py
"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, "src/edge-agent")
import torch, torch.nn.functional as F
from PIL import Image
from torchvision import transforms as T
from page_classifier import DINOV2_HUB_REPO, DINOV2_MODEL_NAME

NORM=T.Normalize(mean=[0.485,0.456,0.406],std=[0.229,0.224,0.225])
FD=Path('tests/fixtures/frames')
sys.path.insert(0, str(Path('.').resolve()))
from tools.reference_screens import reference_screens  # noqa: E402
reg=json.loads((FD/'registry.json').read_text(encoding='utf-8'))
new=json.loads((FD/'relocalized.json').read_text(encoding='utf-8'))
model=torch.hub.load(DINOV2_HUB_REPO,DINOV2_MODEL_NAME); model.eval()
random.seed(0)

def embed(img):
    x=NORM(T.ToTensor()(img.convert('RGB').resize((224,224),Image.Resampling.BICUBIC)))
    with torch.no_grad(): t=model.forward_features(x.unsqueeze(0))['x_norm_patchtokens'][0]
    return F.normalize(F.normalize(t,dim=-1).mean(0),dim=0)
def rect_of(e): return new[e['frame']]['rect'] if e['frame'] in new else e.get('app_rect')

HOLD='20250922-parte01'
train, test = {}, []
for e in reg['frames']:
    if not e.get('video') or not (FD/e['frame']).exists(): continue
    if HOLD in e['video']: test.append(e)
    else: train.setdefault(e['cluster'],[]).append(e)

# cache degli embedding: gli stessi ritagli servono a tutte le varianti
cache={}
def emb_of(e):
    if e['frame'] not in cache:
        rc=rect_of(e)
        cache[e['frame']] = embed(Image.open(FD/e['frame']).crop(tuple(rc))) if rc else None
    return cache[e['frame']]

pages={}
for c,rows in train.items():
    if not c or not c.isdigit(): continue
    v=[x for x in (emb_of(r) for r in rows) if x is not None]
    if len(v)>=3: pages[c]=torch.stack(v)
for n in range(1,10):
    p=reference_screens()[f'screen {n}']
    if p.exists():
        e=embed(Image.open(p)).unsqueeze(0); k=str(n)
        pages[k]=torch.cat([pages[k],e]) if k in pages else e
page_protos={c: F.normalize(v.mean(0),dim=0) for c,v in pages.items()}

def rejects(mode, n=40):
    out={}
    if mode=='uno':
        pool=[r for c in ('altro-bper','altro-app','altro') for r in train.get(c,[])]
        v=[x for x in (emb_of(r) for r in random.sample(pool,min(n,len(pool)))) if x is not None]
        out['SCARTO']=F.normalize(torch.stack(v).mean(0),dim=0)
    elif mode=='per-tipo':
        for c in ('altro-bper','altro-app','altro-nulla'):
            pool=train.get(c,[])
            if len(pool)<3: continue
            v=[x for x in (emb_of(r) for r in random.sample(pool,min(n,len(pool)))) if x is not None]
            if v: out[f'SCARTO:{c}']=F.normalize(torch.stack(v).mean(0),dim=0)
    else:  # k-means sui negativi
        k=int(mode.split('-')[1])
        pool=[r for c in ('altro-bper','altro-app','altro-nulla','altro') for r in train.get(c,[])]
        v=[x for x in (emb_of(r) for r in random.sample(pool,min(240,len(pool)))) if x is not None]
        X=torch.stack(v)
        cent=X[random.sample(range(len(X)),k)].clone()
        for _ in range(15):
            a=(X@cent.T).argmax(1)
            for i in range(k):
                sel=X[a==i]
                if len(sel): cent[i]=F.normalize(sel.mean(0),dim=0)
        for i in range(k): out[f'SCARTO:g{i}']=cent[i]
    return out

def run(mode):
    protos={**page_protos, **rejects(mode)}
    names=sorted(protos)
    M=torch.stack([protos[n] for n in names]); mu=M.mean(0)
    C=F.normalize(M-mu,p=2,dim=1)
    ok=tot=falsi=neg=0
    for e in test:
        q=emb_of(e)
        if q is None: continue
        q=F.normalize(q-mu,dim=0)
        pred=names[int((C@q).argmax())]; truth=e['cluster']
        if truth and truth.isdigit(): tot+=1; ok += (pred==truth)
        else:
            neg+=1; falsi += (not pred.startswith('SCARTO'))
    n_scarti=sum(1 for n in names if n.startswith('SCARTO'))
    print(f'{mode:12} prototipi scarto: {n_scarti:2}   pagine {ok}/{tot} ({100*ok/tot:3.0f}%)   '
          f'falsi positivi {falsi:3}/{neg} ({100*falsi/neg:3.0f}%)')

print('classi pagina con prototipo:', len(page_protos), '\n')
for mode in ('uno','per-tipo','k-4','k-8','k-16','k-24'):
    run(mode)
