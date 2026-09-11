#!/usr/bin/env python3
import csv
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('ZELI_DATA_DIR') or os.getenv('RAILWAY_VOLUME_MOUNT_PATH') or (ROOT / 'data'))
DB_PATH = Path(os.getenv('ZELI_DB_PATH') or (DATA_DIR / 'recruitment.db'))
STATIC = ROOT / 'static'
ADMIN_TOKEN = os.getenv('ZELI_ADMIN_TOKEN')
if not ADMIN_TOKEN:
    if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('ZELI_ENV') == 'production':
        raise RuntimeError('ZELI_ADMIN_TOKEN is required in production')
    ADMIN_TOKEN = 'zeli-local-admin'
PORT = int(os.getenv('PORT', '8080'))
PUBLIC_SEARCH_TIMEOUT = float(os.getenv('ZELI_SEARCH_TIMEOUT', '12'))
USER_AGENT = os.getenv('ZELI_USER_AGENT', 'ZeliRecruitment/0.4 (+operator-supervised research)')

STOPWORDS = {
    'the','and','for','with','from','that','this','role','work','years','year','experience','relevant','senior',
    'junior','lead','manager','project','projects','candidate','candidates','based','able','should','have','into',
    'are','our','who','you','your','their','they','job','position','team','teams','within','across','will','can',
    'of','in','on','to','a','an','or','as','at','is','be','it','by','we','has','any','not','may','more','than'
}

TECH_ROLE_TOKENS = {'software','developer','engineer','engineering','data','devops','security','cloud','backend','frontend','fullstack','python','java','javascript','machine','ml','ai'}

# ---------------- basics ----------------
def now():
    return datetime.now(timezone.utc).isoformat()

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def jdump(v):
    return json.dumps(v, ensure_ascii=False)

def jload(v, default=None):
    if v in (None, ''):
        return default
    try:
        return json.loads(v)
    except Exception:
        return default

def slug(s):
    s = (s or '').strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'anonymous'

def clean_text(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()

def tokens(s, min_len=3):
    out=[]
    for t in re.findall(r"[a-zA-ZÀ-ÿ0-9+#.]{%d,}" % min_len, (s or '').lower()):
        t=t.strip('.').lower()
        if t and t not in STOPWORDS and not t.isdigit(): out.append(t)
    return out

def bounded(v, low, high):
    return max(low, min(high, v))

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con=db(); cur=con.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS runs(
      id TEXT PRIMARY KEY,
      recruiter_token TEXT NOT NULL,
      recruiter_name TEXT,
      recruiter_key TEXT NOT NULL,
      role TEXT NOT NULL,
      brief TEXT NOT NULL,
      context TEXT,
      criteria_json TEXT NOT NULL,
      search_plan_json TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      published_at TEXT
    );
    CREATE TABLE IF NOT EXISTS candidates(
      id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      name TEXT NOT NULL,
      title TEXT,
      company TEXT,
      location TEXT,
      profile_url TEXT,
      summary TEXT,
      skills_json TEXT NOT NULL DEFAULT '[]',
      evidence_json TEXT NOT NULL,
      verify_json TEXT NOT NULL,
      base_score REAL NOT NULL,
      learned_adjustment REAL NOT NULL DEFAULT 0,
      score REAL NOT NULL,
      evidence_coverage REAL NOT NULL,
      search_round INTEGER NOT NULL,
      operator_status TEXT NOT NULL DEFAULT 'PENDING',
      operator_note TEXT,
      rank_order INTEGER NOT NULL DEFAULT 999,
      published INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(run_id) REFERENCES runs(id)
    );
    CREATE TABLE IF NOT EXISTS candidate_sources(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      candidate_id TEXT NOT NULL,
      source_type TEXT NOT NULL,
      source_url TEXT,
      source_title TEXT,
      snippet TEXT,
      query TEXT,
      search_round INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS discovery_queries(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      search_round INTEGER NOT NULL,
      adapter TEXT NOT NULL,
      query TEXT NOT NULL,
      status TEXT NOT NULL,
      hits INTEGER NOT NULL DEFAULT 0,
      error TEXT,
      duration_ms INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY(run_id) REFERENCES runs(id)
    );
    CREATE TABLE IF NOT EXISTS internal_people(
      id TEXT PRIMARY KEY,
      recruiter_key TEXT NOT NULL,
      name TEXT NOT NULL,
      title TEXT,
      company TEXT,
      location TEXT,
      profile_url TEXT,
      summary TEXT,
      skills_json TEXT NOT NULL DEFAULT '[]',
      source_label TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_internal_people_recruiter ON internal_people(recruiter_key);
    CREATE TABLE IF NOT EXISTS recruiter_signals(
      recruiter_key TEXT NOT NULL,
      dimension TEXT NOT NULL,
      value TEXT NOT NULL,
      yes_count INTEGER NOT NULL DEFAULT 0,
      no_count INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(recruiter_key, dimension, value)
    );
    CREATE TABLE IF NOT EXISTS decisions(
      run_id TEXT NOT NULL,
      candidate_id TEXT NOT NULL,
      choice TEXT NOT NULL,
      reason TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(run_id,candidate_id)
    );
    CREATE TABLE IF NOT EXISTS pipeline(
      run_id TEXT NOT NULL,
      candidate_id TEXT NOT NULL,
      status TEXT NOT NULL,
      note TEXT,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(run_id,candidate_id)
    );
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      actor TEXT NOT NULL,
      type TEXT NOT NULL,
      payload_json TEXT,
      created_at TEXT NOT NULL
    );
    ''')
    # Backward-compatible run-level sourcing constraints.
    run_cols={row['name'] for row in con.execute('PRAGMA table_info(runs)').fetchall()}
    if 'location' not in run_cols:
        con.execute('ALTER TABLE runs ADD COLUMN location TEXT')
    if 'work_setup' not in run_cols:
        con.execute('ALTER TABLE runs ADD COLUMN work_setup TEXT')
    con.commit(); con.close()

# ---------------- agent / semi-engine ----------------
def compile_brief(role, brief, context='', location='', work_setup=''):
    text=(brief+' '+context).lower()
    must=[]; signals=[]; equivalents=[]; verify=[]; exclusions=[]
    m=re.search(r'(?:at least|minimum(?: of)?|min\.?|minimum)\s+(\d+)\+?\s+years?', text)
    if not m: m=re.search(r'(\d+)\+\s+years?', text)
    if m: must.append(f"{m.group(1)}+ years of relevant experience")
    location=clean_text(location)
    work_setup=clean_text(work_setup)
    if location:
        setup_suffix=f' ({work_setup})' if work_setup else ''
        must.append(f'Location / work setup compatible with {location}{setup_suffix}')
    elif any(k in text for k in ['based in','location','locally','onsite','on-site','hybrid','remote']):
        must.append('Location / work setup compatible with the role')
    signal_map=[
      ('vendor','Vendor coordination experience'),('client','Client-facing communication'),
      ('multidisciplinary','Multidisciplinary project ownership'),('cross-functional','Cross-functional project ownership'),
      ('epc','EPC project exposure'),('schedule','Project scheduling / planning'),
      ('procurement','Procurement exposure'),('sales','Relevant sales experience'),
      ('recruit','Recruitment / talent sourcing experience'),('python','Python experience'),
      ('javascript','JavaScript experience'),('cloud','Cloud experience'),('manufactur','Manufacturing exposure'),
      ('logistic','Logistics exposure'),('finance','Finance / financial services exposure')
    ]
    for patt,label in signal_map:
        if patt in text and label not in signals: signals.append(label)
    eq=re.search(r'(?:equivalent titles?(?: may include)?|similar titles?|also consider)\s*[:\-]?\s*([^\.\n]+)', context, re.I)
    if eq:
        equivalents += [x.strip() for x in re.split(r',|\bor\b|/', eq.group(1)) if x.strip()]
    equivalents = [role] + [x for x in equivalents if x.lower()!=role.lower()]
    equivalents.append('Adjacent titles with materially similar responsibilities')
    if any(k in text for k in ['exclude','do not consider','avoid','must not']):
        exclusions.append('Apply explicit exclusions stated in the brief/context')
    verify += [
      'Requirements not visible in available evidence should be verified, not assumed absent',
      'Interest, availability and compensation expectations'
    ]
    if not must: must=['Core experience and responsibilities stated in the brief']
    if not signals: signals=['Relevant functional experience','Evidence of progression and scope']
    return {'must':must,'signals':signals,'equivalent_titles':equivalents,'verify':verify,'exclusions':exclusions}

def extract_location_hint(text):
    # Legacy fallback for older runs that predate explicit location fields.
    text=(text or '').lower()
    for loc in ['panama','costa rica','colombia','mexico','united states','usa','uk','united kingdom','spain','canada','latam','latin america']:
        if loc in text: return loc.title()
    return ''

def build_search_plan(criteria, role, brief='', context='', location='', work_setup=''):
    eq=[x for x in criteria.get('equivalent_titles',[]) if 'Adjacent titles' not in x]
    signals=criteria.get('signals',[])[:4]
    location=clean_text(location) or extract_location_hint(brief+' '+context)
    work_setup=clean_text(work_setup)
    location_term=clean_text(f'{location} {work_setup}')
    signal_terms=[' '.join(tokens(s)[:2]) for s in signals if tokens(s)]
    rounds=[]
    q1=[]
    for t in eq[:3] or [role]:
        suffix=' '.join(signal_terms[:2])
        q=clean_text(f'"{t}" {suffix} {location_term}')
        q1.append(q)
    rounds.append({'round':1,'strategy':'Narrow evidence search','queries':q1})
    q2=[clean_text(f'"{t}" {location_term}') for t in (eq[:5] or [role])]
    rounds.append({'round':2,'strategy':'Relax supporting keywords','queries':q2})
    r_tokens=tokens(role)
    broad=' '.join(r_tokens[-2:] or r_tokens or [role])
    q3=[clean_text(f'{broad} {location_term}'), clean_text(f'{broad} {signal_terms[0] if signal_terms else ""} {location_term}')]
    rounds.append({'round':3,'strategy':'Broaden adjacent titles','queries':list(dict.fromkeys(q3))})
    locator=[]
    for t in eq[:3] or [role]:
        locator.append(clean_text(f'site:linkedin.com/in "{t}" {location_term}'))
    return {'rounds':rounds,'profile_locator_queries':locator,'location_hint':location,'work_setup':work_setup}

def tri_status(candidate_text, criterion):
    ct=(candidate_text or '').lower(); cr=(criterion or '').lower()
    # Explicit years are handled numerically instead of keyword matching.
    req_years=re.search(r'(\d+)\+?\s*years?',cr)
    if req_years:
        cand_years=[int(x) for x in re.findall(r'(\d+)\+?\s*years?',ct)]
        if cand_years and max(cand_years)>=int(req_years.group(1)): return 'MET'
        return 'UNKNOWN'
    # Location criteria often contain generic wording; a named target is stronger evidence.
    places=['panama','costa rica','colombia','mexico','united states','usa','united kingdom','uk','spain','canada','latam','latin america']
    named=[p for p in places if p in cr]
    if named:
        return 'MET' if any(p in ct for p in named) else 'UNKNOWN'
    cr_tokens=[t for t in tokens(cr,4) if t not in {'core','requirements','stated','brief','compatible','location','setup'}]
    if not cr_tokens: return 'UNKNOWN'
    hits=[t for t in cr_tokens if t in ct]
    if len(hits)>=max(1,math.ceil(len(cr_tokens)*0.30)): return 'MET'
    return 'UNKNOWN'

def get_signal_rows(con, recruiter_key):
    return con.execute('select * from recruiter_signals where recruiter_key=?',(recruiter_key,)).fetchall()

def signal_weight(yes_count,no_count):
    # Bayesian-smoothed preference, modest by design. A tiny data set cannot overpower brief fit.
    n=yes_count+no_count
    if n<1: return 0.0
    preference=((yes_count+1)/(n+2)-0.5)*2
    confidence=min(1.0,n/5)
    return preference*confidence

def learned_adjustment(con, recruiter_key, c, evidence):
    rows=get_signal_rows(con,recruiter_key)
    if not rows: return 0.0, []
    title_t=set(tokens(c.get('title',''))); loc_t=set(tokens(c.get('location',''))); company=clean_text(c.get('company','')).lower()
    met_criteria={clean_text(x.get('criterion','')).lower() for x in evidence if x.get('status')=='MET'}
    total=0.0; matched=[]
    for r in rows:
        val=r['value']; dim=r['dimension']; match=False
        if dim=='title_token' and val in title_t: match=True
        elif dim=='location_token' and val in loc_t: match=True
        elif dim=='company' and val==company and val: match=True
        elif dim=='criterion' and val in met_criteria: match=True
        if match:
            w=signal_weight(r['yes_count'],r['no_count'])
            if abs(w)>0.01:
                total += 3.0*w
                matched.append({'dimension':dim,'value':val,'weight':round(3.0*w,2),'yes':r['yes_count'],'no':r['no_count']})
    return round(bounded(total,-12,12),1), matched

def score_candidate(con, recruiter_key, criteria, c):
    text=' '.join([c.get('title',''),c.get('company',''),c.get('location',''),c.get('summary',''),' '.join(c.get('skills',[]) or [])])
    evidence=[]; verify=[]
    must=criteria.get('must',[]); sig=criteria.get('signals',[])
    met_must=0
    for cr in must:
        st=tri_status(text,cr)
        if st=='MET':
            met_must+=1; evidence.append({'criterion':cr,'status':'MET','evidence':f'Available evidence contains signals aligned with: {cr}'})
        else:
            verify.append({'criterion':cr,'status':'UNKNOWN','evidence':'Not explicit in available source evidence'})
    met_sig=0
    for cr in sig:
        st=tri_status(text,cr)
        if st=='MET':
            met_sig+=1; evidence.append({'criterion':cr,'status':'MET','evidence':f'Available evidence contains signals aligned with: {cr}'})
        else:
            verify.append({'criterion':cr,'status':'UNKNOWN','evidence':'Not explicit in available source evidence'})
    exact_titles=[t for t in criteria.get('equivalent_titles',[]) if 'Adjacent' not in t]
    title_l=c.get('title','').lower()
    title_score=15 if any(t.lower() in title_l or (title_l and title_l in t.lower()) for t in exact_titles) else 8
    must_score=50*(met_must/max(1,len(must)))
    sig_score=25*(met_sig/max(1,len(sig)))
    loc_needed=any('location' in m.lower() for m in must)
    loc_score=10 if not loc_needed else (10 if c.get('location') else 5)
    base=round(min(100,must_score+sig_score+title_score+loc_score),1)
    coverage=round(100*(len(evidence)/(len(must)+len(sig))),1) if (must or sig) else 0
    adjustment, matched=learned_adjustment(con,recruiter_key,c,evidence)
    final=round(bounded(base+adjustment,0,100),1)
    return base,adjustment,final,coverage,evidence,verify,matched

# ---------------- feedback learning ----------------
def upsert_signal(con,recruiter_key,dimension,value,choice):
    value=clean_text(value).lower()
    if not value or len(value)>180: return
    ts=now()
    con.execute('''insert into recruiter_signals(recruiter_key,dimension,value,yes_count,no_count,updated_at)
      values(?,?,?,?,?,?)
      on conflict(recruiter_key,dimension,value) do update set
      yes_count=yes_count+excluded.yes_count,
      no_count=no_count+excluded.no_count,
      updated_at=excluded.updated_at''',
      (recruiter_key,dimension,value,1 if choice=='yes' else 0,1 if choice=='no' else 0,ts))

def learn_from_decision(con,run_id,candidate_id,choice):
    run=con.execute('select recruiter_key from runs where id=?',(run_id,)).fetchone()
    c=con.execute('select * from candidates where id=? and run_id=?',(candidate_id,run_id)).fetchone()
    if not run or not c: return
    for t in list(dict.fromkeys(tokens(c['title'])))[:8]: upsert_signal(con,run['recruiter_key'],'title_token',t,choice)
    for t in list(dict.fromkeys(tokens(c['location'])))[:5]: upsert_signal(con,run['recruiter_key'],'location_token',t,choice)
    if c['company']: upsert_signal(con,run['recruiter_key'],'company',c['company'],choice)
    for e in jload(c['evidence_json'],[]) or []:
        if e.get('status')=='MET': upsert_signal(con,run['recruiter_key'],'criterion',e.get('criterion',''),choice)

# ---------------- source adapters ----------------
def http_json(url, method='GET', headers=None, body=None):
    data=None
    if body is not None:
        data=json.dumps(body).encode('utf-8')
    req=Request(url,data=data,method=method,headers={'User-Agent':USER_AGENT, **(headers or {})})
    with urlopen(req,timeout=PUBLIC_SEARCH_TIMEOUT) as resp:
        return json.loads(resp.read().decode('utf-8','replace'))

def public_search_provider():
    if os.getenv('BRAVE_SEARCH_API_KEY'): return 'brave'
    if os.getenv('SERPER_API_KEY'): return 'serper'
    if os.getenv('SEARXNG_URL'): return 'searxng'
    return None

def source_health(con=None,recruiter_key=None):
    own=False
    if con is None: con=db(); own=True
    count=0
    if recruiter_key:
        count=con.execute('select count(*) n from internal_people where recruiter_key=?',(recruiter_key,)).fetchone()['n']
    provider=public_search_provider()
    out={
      'internal_pool':{'available':count>0,'records':count,'description':'Recruiter-owned candidate records / CSV'},
      'public_web':{'available':bool(provider),'provider':provider,'description':'Search-engine/API discovery across the public web'},
      'github':{'available':True,'authenticated':bool(os.getenv('GITHUB_TOKEN')),'description':'Optional technical-talent signal source'},
      'manual':{'available':True,'description':'Operator-added profile/evidence'}
    }
    if own: con.close()
    return out

def internal_search(con,recruiter_key,query,limit=12):
    rows=con.execute('select * from internal_people where recruiter_key=?',(recruiter_key,)).fetchall()
    q=set(tokens(query))
    scored=[]
    for r in rows:
        text=' '.join([r['name'],r['title'] or '',r['company'] or '',r['location'] or '',r['summary'] or '',' '.join(jload(r['skills_json'],[]) or [])])
        tt=set(tokens(text))
        overlap=len(q & tt)
        phrase_bonus=2 if clean_text(query).lower() in text.lower() else 0
        s=overlap+phrase_bonus
        if s>0: scored.append((s,r))
    scored.sort(key=lambda x:(-x[0],x[1]['name'].lower()))
    hits=[]
    for score,r in scored[:limit]:
        hits.append({
          'name':r['name'],'title':r['title'] or '','company':r['company'] or '','location':r['location'] or '',
          'profile_url':r['profile_url'] or '','summary':r['summary'] or '','skills':jload(r['skills_json'],[]) or [],
          'source_type':'internal_pool','source_url':r['profile_url'] or '',
          'source_title':f"{r['name']} · {r['source_label'] or 'Internal candidate pool'}",
          'snippet':r['summary'] or 'Recruiter-owned candidate record','query':query,'discovery_score':score
        })
    return hits

def parse_web_identity(title,url,snippet):
    raw=re.sub(r'\s+\|\s+LinkedIn.*$','',title or '',flags=re.I)
    parts=[clean_text(x) for x in re.split(r'\s+[\-|–|—|·]\s+',raw) if clean_text(x)]
    name=parts[0] if parts else clean_text(title)[:120]
    job=''; company=''
    if len(parts)>=2: job=parts[1]
    if len(parts)>=3: company=parts[2]
    if not name or len(name.split())>8:
        name=(urlparse(url).path.rstrip('/').split('/')[-1].replace('-',' ').title() if url else 'Public web result')
    return name[:140],job[:180],company[:180]

def public_web_search(query,limit=10):
    provider=public_search_provider()
    if not provider: raise RuntimeError('No public web search provider configured')
    organic=[]
    if provider=='brave':
        url='https://api.search.brave.com/res/v1/web/search?'+urlencode({'q':query,'count':min(limit,20)})
        data=http_json(url,headers={'Accept':'application/json','X-Subscription-Token':os.environ['BRAVE_SEARCH_API_KEY']})
        organic=(data.get('web') or {}).get('results') or []
        norm=[{'title':x.get('title',''),'link':x.get('url',''),'snippet':x.get('description','')} for x in organic]
    elif provider=='serper':
        data=http_json('https://google.serper.dev/search',method='POST',headers={'X-API-KEY':os.environ['SERPER_API_KEY'],'Content-Type':'application/json'},body={'q':query,'num':min(limit,20)})
        organic=data.get('organic') or []
        norm=[{'title':x.get('title',''),'link':x.get('link',''),'snippet':x.get('snippet','')} for x in organic]
    else:
        base=os.environ['SEARXNG_URL'].rstrip('/')
        data=http_json(base+'/search?'+urlencode({'q':query,'format':'json'}))
        organic=(data.get('results') or [])[:limit]
        norm=[{'title':x.get('title',''),'link':x.get('url',''),'snippet':x.get('content','')} for x in organic]
    hits=[]
    for x in norm[:limit]:
        url=x.get('link',''); title=x.get('title',''); snippet=x.get('snippet','')
        name,job,company=parse_web_identity(title,url,snippet)
        hits.append({'name':name,'title':job,'company':company,'location':'','profile_url':url,'summary':snippet,'skills':[],
          'source_type':'public_web','source_url':url,'source_title':title,'snippet':snippet,'query':query,'provider':provider})
    return hits

def github_search(query, location_hint='', limit=8):
    # This is intentionally a supplemental adapter. GitHub is a strong evidence source for some technical roles, not a general people directory.
    qt=tokens(query)
    if not (set(qt)&TECH_ROLE_TOKENS): return []
    gh_query=' '.join([t for t in qt if t in TECH_ROLE_TOKENS][:2])
    if location_hint and location_hint.lower() not in {'latam','latin america'}:
        gh_query += f' location:"{location_hint}"'
    headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    if os.getenv('GITHUB_TOKEN'): headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    data=http_json('https://api.github.com/search/users?'+urlencode({'q':gh_query or 'engineer','per_page':min(limit,10)}),headers=headers)
    hits=[]
    for item in (data.get('items') or [])[:limit]:
        login=item.get('login',''); profile=item.get('html_url',''); details={}
        try: details=http_json(item.get('url'),headers=headers)
        except Exception: pass
        name=details.get('name') or login
        bio=details.get('bio') or ''
        company=(details.get('company') or '').lstrip('@')
        loc=details.get('location') or ''
        hits.append({'name':name,'title':'','company':company,'location':loc,'profile_url':profile,
          'summary':clean_text(f"{bio} Public repositories: {details.get('public_repos','')}. Followers: {details.get('followers','')}"),
          'skills':[],'source_type':'github','source_url':profile,'source_title':f'{name} on GitHub','snippet':bio,'query':query})
    return hits

def canonical_key(hit):
    url=clean_text(hit.get('profile_url','')).lower().rstrip('/')
    if url: return 'url:'+url
    name=clean_text(hit.get('name','')).lower(); company=clean_text(hit.get('company','')).lower()
    return 'person:'+re.sub(r'\W+','',name)+'|'+re.sub(r'\W+','',company)

def candidate_existing(con,run_id,hit):
    url=clean_text(hit.get('profile_url','')).lower().rstrip('/')
    if url:
        row=con.execute('select * from candidates where run_id=? and lower(rtrim(profile_url,"/"))=?',(run_id,url)).fetchone()
        if row: return row
    name=clean_text(hit.get('name','')).lower(); comp=clean_text(hit.get('company','')).lower()
    return con.execute('select * from candidates where run_id=? and lower(name)=? and lower(coalesce(company,""))=?',(run_id,name,comp)).fetchone()

def add_source(con,candidate_id,hit,search_round):
    src_url=clean_text(hit.get('source_url',''))
    snippet=clean_text(hit.get('snippet',''))[:2500]
    exists=con.execute('select 1 from candidate_sources where candidate_id=? and source_type=? and coalesce(source_url,"")=? and coalesce(snippet,"")=?',
      (candidate_id,hit.get('source_type','unknown'),src_url,snippet)).fetchone()
    if exists: return
    con.execute('''insert into candidate_sources(candidate_id,source_type,source_url,source_title,snippet,query,search_round,created_at)
      values(?,?,?,?,?,?,?,?)''',(candidate_id,hit.get('source_type','unknown'),src_url,clean_text(hit.get('source_title',''))[:500],snippet,clean_text(hit.get('query',''))[:1000],search_round,now()))

def stage_hit(con,run,criteria,hit,search_round):
    c={
      'name':clean_text(hit.get('name','')) or 'Public web result',
      'title':clean_text(hit.get('title','')),
      'company':clean_text(hit.get('company','')),
      'location':clean_text(hit.get('location','')),
      'profile_url':clean_text(hit.get('profile_url','')),
      'summary':clean_text(hit.get('summary','')),
      'skills':hit.get('skills') or []
    }
    existing=candidate_existing(con,run['id'],c)
    if existing:
        # Merge evidence conservatively: keep operator edits; append unseen snippet to summary.
        old_summary=existing['summary'] or ''
        new_summary=c['summary']
        merged=old_summary
        if new_summary and new_summary.lower() not in old_summary.lower(): merged=clean_text(old_summary+' '+new_summary)
        merged_skills=list(dict.fromkeys((jload(existing['skills_json'],[]) or []) + c['skills']))
        merged_c={
          'name':existing['name'], 'title':existing['title'] or c['title'], 'company':existing['company'] or c['company'],
          'location':existing['location'] or c['location'], 'profile_url':existing['profile_url'] or c['profile_url'],
          'summary':merged, 'skills':merged_skills
        }
        base,adj,final,cov,evidence,verify,_=score_candidate(con,run['recruiter_key'],criteria,merged_c)
        con.execute('''update candidates set title=?,company=?,location=?,profile_url=?,summary=?,skills_json=?,evidence_json=?,verify_json=?,
          base_score=?,learned_adjustment=?,score=?,evidence_coverage=?,search_round=min(search_round,?),updated_at=? where id=?''',
          (merged_c['title'],merged_c['company'],merged_c['location'],merged_c['profile_url'],merged,jdump(merged_skills),jdump(evidence),jdump(verify),base,adj,final,cov,search_round,now(),existing['id']))
        add_source(con,existing['id'],hit,search_round)
        return existing['id'],False
    base,adj,final,cov,evidence,verify,_=score_candidate(con,run['recruiter_key'],criteria,c)
    cid='cand_'+secrets.token_hex(6)
    rank=con.execute('select coalesce(max(rank_order),0)+1 n from candidates where run_id=?',(run['id'],)).fetchone()['n']
    con.execute('''insert into candidates(id,run_id,name,title,company,location,profile_url,summary,skills_json,evidence_json,verify_json,
      base_score,learned_adjustment,score,evidence_coverage,search_round,operator_status,rank_order,created_at,updated_at)
      values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (cid,run['id'],c['name'],c['title'],c['company'],c['location'],c['profile_url'],c['summary'],jdump(c['skills']),jdump(evidence),jdump(verify),base,adj,final,cov,search_round,'PENDING',rank,now(),now()))
    add_source(con,cid,hit,search_round)
    return cid,True

def execute_discovery(run_id, adapters, include_locator=True, per_query_limit=8, max_new_candidates=40):
    con=db(); run=con.execute('select * from runs where id=?',(run_id,)).fetchone()
    if not run: con.close(); raise KeyError('run not found')
    criteria=jload(run['criteria_json'],{}) or {}; plan=jload(run['search_plan_json'],{}) or {}
    rounds=plan.get('rounds') if isinstance(plan,dict) else plan
    rounds=rounds or []
    created=0; merged=0; total_hits=0; errors=[]
    health=source_health(con,run['recruiter_key'])
    adapter_order=[a for a in adapters if a in {'internal_pool','public_web','github'}]
    for rd in rounds:
        if created>=max_new_candidates: break
        queries=rd.get('queries',[])
        if include_locator and rd.get('round')==2 and 'public_web' in adapter_order:
            queries=queries+(plan.get('profile_locator_queries') or [])
        for query in list(dict.fromkeys(queries)):
            if created>=max_new_candidates: break
            for adapter in adapter_order:
                if created>=max_new_candidates: break
                start=time.time(); status='OK'; err=''; hits=[]
                try:
                    if adapter=='internal_pool':
                        hits=internal_search(con,run['recruiter_key'],query,per_query_limit)
                    elif adapter=='public_web':
                        if not health['public_web']['available']: raise RuntimeError('public web provider not configured')
                        hits=public_web_search(query,per_query_limit)
                    elif adapter=='github':
                        hits=github_search(query,plan.get('location_hint',''),min(per_query_limit,8))
                except Exception as e:
                    status='ERROR'; err=str(e)[:800]; errors.append({'adapter':adapter,'query':query,'error':err})
                duration=int((time.time()-start)*1000)
                con.execute('insert into discovery_queries(run_id,search_round,adapter,query,status,hits,error,duration_ms,created_at) values(?,?,?,?,?,?,?,?,?)',
                  (run_id,int(rd.get('round') or 1),adapter,query,status,len(hits),err,duration,now()))
                for hit in hits:
                    total_hits+=1
                    _,is_new=stage_hit(con,run,criteria,hit,int(rd.get('round') or 1))
                    if is_new: created+=1
                    else: merged+=1
                    if created>=max_new_candidates: break
    con.execute("update runs set status='OPERATOR_REVIEW',updated_at=? where id=?",(now(),run_id))
    log_event(con,run_id,'engine','DISCOVERY_COMPLETED',{'adapters':adapter_order,'created':created,'merged':merged,'hits':total_hits,'errors':errors[:10]})
    con.commit(); con.close()
    return {'created':created,'merged':merged,'hits':total_hits,'errors':errors,'adapters':adapter_order}

# ---------------- internal pool import ----------------
def import_internal_people(con,recruiter_key,records,source_label='Imported candidate pool'):
    inserted=0; updated=0; ts=now()
    for rec in records:
        name=clean_text(rec.get('name') or rec.get('full_name') or rec.get('candidate') or '')
        if not name: continue
        profile=clean_text(rec.get('profile_url') or rec.get('linkedin_url') or rec.get('url') or '')
        company=clean_text(rec.get('company') or rec.get('employer') or '')
        raw_id=profile or (name.lower()+'|'+company.lower()+'|'+clean_text(rec.get('title') or '').lower())
        pid='pool_'+hashlib.sha1((recruiter_key+'|'+raw_id).encode()).hexdigest()[:16]
        skills=rec.get('skills') or []
        if isinstance(skills,str): skills=[x.strip() for x in re.split(r'[,;|]',skills) if x.strip()]
        vals=(pid,recruiter_key,name,clean_text(rec.get('title') or rec.get('job_title') or ''),company,
              clean_text(rec.get('location') or ''),profile,clean_text(rec.get('summary') or rec.get('notes') or rec.get('experience') or ''),
              jdump(skills),clean_text(rec.get('source_label') or source_label),ts,ts)
        existed=con.execute('select 1 from internal_people where id=?',(pid,)).fetchone()
        con.execute('''insert into internal_people(id,recruiter_key,name,title,company,location,profile_url,summary,skills_json,source_label,created_at,updated_at)
          values(?,?,?,?,?,?,?,?,?,?,?,?) on conflict(id) do update set
          name=excluded.name,title=excluded.title,company=excluded.company,location=excluded.location,profile_url=excluded.profile_url,
          summary=excluded.summary,skills_json=excluded.skills_json,source_label=excluded.source_label,updated_at=excluded.updated_at''',vals)
        if existed: updated+=1
        else: inserted+=1
    return inserted,updated

# ---------------- payloads ----------------
def log_event(con,run_id,actor,type_,payload):
    con.execute('insert into events(run_id,actor,type,payload_json,created_at) values(?,?,?,?,?)',(run_id,actor,type_,jdump(payload),now()))

def learning_payload(con,recruiter_key,limit=50):
    rows=con.execute('''select * from recruiter_signals where recruiter_key=? order by (yes_count+no_count) desc, updated_at desc limit ?''',(recruiter_key,limit)).fetchall()
    out=[]
    for r in rows:
        out.append({**dict(r),'preference':round(signal_weight(r['yes_count'],r['no_count']),3)})
    return out

def run_payload(run_id, include_private=False):
    con=db(); r=con.execute('select * from runs where id=?',(run_id,)).fetchone()
    if not r: con.close(); return None
    cand_rows=con.execute('select * from candidates where run_id=? order by rank_order, score desc',(run_id,)).fetchall()
    dec={x['candidate_id']:dict(x) for x in con.execute('select * from decisions where run_id=?',(run_id,)).fetchall()}
    pipe={x['candidate_id']:dict(x) for x in con.execute('select * from pipeline where run_id=?',(run_id,)).fetchall()}
    plan=jload(r['search_plan_json'],{}) or {}
    out={'id':r['id'],'recruiter_name':r['recruiter_name'],'recruiter_key':r['recruiter_key'],'role':r['role'],'location':r['location'] or '',
      'work_setup':r['work_setup'] or '','brief':r['brief'],'context':r['context'],
      'criteria':jload(r['criteria_json'],{}),'search_plan':plan,'status':r['status'],'created_at':r['created_at'],'updated_at':r['updated_at'],'published_at':r['published_at'],'candidates':[]}
    for c in cand_rows:
        if not include_private and not c['published']: continue
        sources=[dict(x) for x in con.execute('select source_type,source_url,source_title,snippet,query,search_round,created_at from candidate_sources where candidate_id=? order by id',(c['id'],)).fetchall()]
        item={'id':c['id'],'name':c['name'],'title':c['title'],'company':c['company'],'location':c['location'],'profile_url':c['profile_url'],
          'evidence':jload(c['evidence_json'],[]) or [],'verify':jload(c['verify_json'],[]) or [],'decision':dec.get(c['id']),'pipeline':pipe.get(c['id'])}
        if include_private:
            item.update({'summary':c['summary'],'skills':jload(c['skills_json'],[]) or [],'base_score':c['base_score'],'learned_adjustment':c['learned_adjustment'],
              'score':c['score'],'evidence_coverage':c['evidence_coverage'],'search_round':c['search_round'],'operator_status':c['operator_status'],
              'operator_note':c['operator_note'],'rank_order':c['rank_order'],'published':bool(c['published']),'sources':sources})
        out['candidates'].append(item)
    if include_private:
        out['events']=[{**dict(x),'payload':jload(x['payload_json'],{})} for x in con.execute('select * from events where run_id=? order by id desc limit 120',(run_id,)).fetchall()]
        out['discovery_queries']=[dict(x) for x in con.execute('select * from discovery_queries where run_id=? order by id desc limit 200',(run_id,)).fetchall()]
        out['source_health']=source_health(con,r['recruiter_key'])
        out['learning']=learning_payload(con,r['recruiter_key'])
    con.close(); return out

# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    server_version='ZeliRecruitment/0.4'
    def send_json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode('utf-8'); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def send_file(self,path,ctype='text/html; charset=utf-8'):
        p=STATIC/path
        if not p.exists(): self.send_error(404); return
        b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def body(self):
        n=int(self.headers.get('Content-Length','0')); raw=self.rfile.read(n) if n else b'{}'
        try:return json.loads(raw)
        except:return {}
    def admin_ok(self,qs=None):
        token=self.headers.get('X-Admin-Token') or (qs or {}).get('admin_token',[''])[0]
        return bool(token) and hmac.compare_digest(token,ADMIN_TOKEN)
    def recruiter_ok(self,run_id,qs=None):
        tok=self.headers.get('X-Run-Token') or (qs or {}).get('token',[''])[0]
        con=db(); r=con.execute('select recruiter_token from runs where id=?',(run_id,)).fetchone(); con.close()
        return bool(r and tok and hmac.compare_digest(tok,r['recruiter_token']))
    def do_GET(self):
        u=urlparse(self.path); path=u.path; qs=parse_qs(u.query)
        if path=='/health': return self.send_json({'ok':True,'service':'zeli-recruitment','version':'0.4'})
        if path in ['/','/index.html']: return self.send_file('index.html')
        if path in ['/admin','/admin.html']: return self.send_file('admin.html')
        if path=='/api/admin/runs':
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            con=db(); rows=con.execute('select id,recruiter_name,recruiter_key,role,status,created_at,updated_at,published_at from runs order by created_at desc').fetchall(); con.close(); return self.send_json([dict(x) for x in rows])
        if path=='/api/admin/source-health':
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            recruiter_key=(qs.get('recruiter_key') or [''])[0]; return self.send_json(source_health(recruiter_key=recruiter_key))
        if path=='/api/admin/internal-pool':
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rk=(qs.get('recruiter_key') or [''])[0]
            con=db(); rows=con.execute('select id,recruiter_key,name,title,company,location,profile_url,summary,skills_json,source_label,updated_at from internal_people where recruiter_key=? order by updated_at desc limit 500',(rk,)).fetchall(); con.close()
            return self.send_json([{**dict(x),'skills':jload(x['skills_json'],[]) or []} for x in rows])
        m=re.fullmatch(r'/api/admin/runs/([^/]+)',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            p=run_payload(m.group(1),True); return self.send_json(p or {'error':'not found'},200 if p else 404)
        m=re.fullmatch(r'/api/runs/([^/]+)',path)
        if m:
            rid=m.group(1)
            if not self.recruiter_ok(rid,qs): return self.send_json({'error':'unauthorized'},401)
            p=run_payload(rid,False); return self.send_json(p or {'error':'not found'},200 if p else 404)
        return self.send_error(404)
    def do_POST(self):
        u=urlparse(self.path); path=u.path; qs=parse_qs(u.query); data=self.body()
        if path=='/api/runs':
            role=clean_text(data.get('role')); location=clean_text(data.get('location')); work_setup=clean_text(data.get('work_setup')); brief=clean_text(data.get('brief')); context=clean_text(data.get('context')); name=clean_text(data.get('recruiter_name'))
            if work_setup not in ['On-site','Hybrid','Remote']: work_setup=''
            if not role or not location or not work_setup or not brief: return self.send_json({'error':'role, location, work setup and brief required'},400)
            rid='run_'+secrets.token_hex(6); rtok=secrets.token_urlsafe(20); rkey=slug(name) if name else 'anon-'+secrets.token_hex(4)
            criteria=compile_brief(role,brief,context,location,work_setup); plan=build_search_plan(criteria,role,brief,context,location,work_setup); ts=now()
            con=db(); con.execute('''insert into runs(id,recruiter_token,recruiter_name,recruiter_key,role,location,work_setup,brief,context,criteria_json,search_plan_json,status,created_at,updated_at,published_at)
              values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(rid,rtok,name,rkey,role,location,work_setup,brief,context,jdump(criteria),jdump(plan),'OPERATOR_REVIEW',ts,ts,None));
            log_event(con,rid,'recruiter','BRIEF_SUBMITTED',{}); log_event(con,rid,'engine','CRITERIA_COMPILED',criteria); con.commit(); con.close()
            return self.send_json({'id':rid,'token':rtok,'status':'OPERATOR_REVIEW'},201)
        if path=='/api/admin/internal-pool/import':
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rk=clean_text(data.get('recruiter_key')); records=data.get('records') or []; label=clean_text(data.get('source_label')) or 'Imported candidate pool'
            if not rk or not isinstance(records,list): return self.send_json({'error':'recruiter_key and records[] required'},400)
            con=db(); ins,upd=import_internal_people(con,rk,records,label); con.commit(); con.close(); return self.send_json({'inserted':ins,'updated':upd,'total_received':len(records)},201)
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/discover',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            try:
                result=execute_discovery(m.group(1),data.get('adapters') or ['internal_pool','public_web'],bool(data.get('include_locator',True)),int(data.get('per_query_limit') or 8),int(data.get('max_new_candidates') or 40))
                return self.send_json(result,200)
            except KeyError: return self.send_json({'error':'not found'},404)
            except Exception as e: return self.send_json({'error':str(e)},500)
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/criteria',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rid=m.group(1); criteria=data.get('criteria') or {}
            con=db(); r=con.execute('select role,location,work_setup,brief,context from runs where id=?',(rid,)).fetchone()
            if not r: con.close(); return self.send_json({'error':'not found'},404)
            plan=build_search_plan(criteria,r['role'],r['brief'],r['context'] or '',r['location'] or '',r['work_setup'] or '')
            con.execute('update runs set criteria_json=?,search_plan_json=?,updated_at=? where id=?',(jdump(criteria),jdump(plan),now(),rid)); log_event(con,rid,'operator','CRITERIA_EDITED',criteria); con.commit(); con.close(); return self.send_json({'ok':True})
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/candidates',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rid=m.group(1); con=db(); r=con.execute('select * from runs where id=?',(rid,)).fetchone()
            if not r: con.close(); return self.send_json({'error':'not found'},404)
            hit={k:clean_text(data.get(k)) for k in ['name','title','company','location','profile_url','summary']}; hit['skills']=data.get('skills') or []
            hit.update({'source_type':'manual','source_url':hit['profile_url'],'source_title':'Operator-added evidence','snippet':hit['summary'],'query':'manual operator add'})
            if not hit['name']: con.close(); return self.send_json({'error':'name required'},400)
            cid,new=stage_hit(con,r,jload(r['criteria_json'],{}),hit,int(data.get('search_round') or 1)); log_event(con,rid,'operator','CANDIDATE_ADDED',{'candidate_id':cid,'new':new}); con.commit()
            c=con.execute('select score,evidence_coverage from candidates where id=?',(cid,)).fetchone(); con.close(); return self.send_json({'id':cid,'score':c['score'],'evidence_coverage':c['evidence_coverage'],'new':new},201)
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/candidates/([^/]+)',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rid,cid=m.groups(); action=data.get('action'); con=db(); r=con.execute('select * from runs where id=?',(rid,)).fetchone(); c=con.execute('select * from candidates where id=? and run_id=?',(cid,rid)).fetchone()
            if not r or not c: con.close(); return self.send_json({'error':'not found'},404)
            if action=='approve': con.execute("update candidates set operator_status='APPROVED',updated_at=? where id=?",(now(),cid))
            elif action=='reject': con.execute("update candidates set operator_status='REJECTED',published=0,updated_at=? where id=?",(now(),cid))
            elif action=='note': con.execute('update candidates set operator_note=?,updated_at=? where id=?',(clean_text(data.get('note')),now(),cid))
            elif action=='rank': con.execute('update candidates set rank_order=?,updated_at=? where id=?',(int(data.get('rank_order') or 999),now(),cid))
            elif action=='edit':
                merged={
                  'name':clean_text(data.get('name')) or c['name'],'title':clean_text(data.get('title')),'company':clean_text(data.get('company')),
                  'location':clean_text(data.get('location')),'profile_url':clean_text(data.get('profile_url')),'summary':clean_text(data.get('summary')),
                  'skills':data.get('skills') or []
                }
                base,adj,final,cov,evidence,verify,_=score_candidate(con,r['recruiter_key'],jload(r['criteria_json'],{}),merged)
                con.execute('''update candidates set name=?,title=?,company=?,location=?,profile_url=?,summary=?,skills_json=?,evidence_json=?,verify_json=?,
                  base_score=?,learned_adjustment=?,score=?,evidence_coverage=?,updated_at=? where id=?''',
                  (merged['name'],merged['title'],merged['company'],merged['location'],merged['profile_url'],merged['summary'],jdump(merged['skills']),jdump(evidence),jdump(verify),base,adj,final,cov,now(),cid))
                manual_hit={'source_type':'manual','source_url':merged['profile_url'],'source_title':'Operator-edited evidence','snippet':merged['summary'],'query':'operator edit'}
                add_source(con,cid,manual_hit,c['search_round'])
            else: con.close(); return self.send_json({'error':'bad action'},400)
            log_event(con,rid,'operator','CANDIDATE_'+action.upper(),{'candidate_id':cid}); con.commit(); con.close(); return self.send_json({'ok':True})
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/publish',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rid=m.group(1); con=db(); approved=con.execute("select count(*) n from candidates where run_id=? and operator_status='APPROVED'",(rid,)).fetchone()['n']
            if approved<1: con.close(); return self.send_json({'error':'approve at least one candidate'},400)
            con.execute("update candidates set published=case when operator_status='APPROVED' then 1 else 0 end where run_id=?",(rid,)); con.execute("update runs set status='PUBLISHED',published_at=?,updated_at=? where id=?",(now(),now(),rid)); log_event(con,rid,'operator','SHORTLIST_PUBLISHED',{'count':approved}); con.commit(); con.close(); return self.send_json({'ok':True,'published':approved})
        m=re.fullmatch(r'/api/runs/([^/]+)/decisions',path)
        if m:
            rid=m.group(1)
            if not self.recruiter_ok(rid,qs): return self.send_json({'error':'unauthorized'},401)
            cid=data.get('candidate_id'); choice=data.get('choice'); reason=clean_text(data.get('reason'))
            if choice not in ['yes','no']: return self.send_json({'error':'choice must be yes or no'},400)
            con=db(); pub=con.execute('select published from candidates where id=? and run_id=?',(cid,rid)).fetchone()
            if not pub or not pub['published']: con.close(); return self.send_json({'error':'candidate not published'},400)
            old=con.execute('select choice from decisions where run_id=? and candidate_id=?',(rid,cid)).fetchone(); ts=now()
            con.execute('''insert into decisions(run_id,candidate_id,choice,reason,created_at,updated_at) values(?,?,?,?,?,?)
              on conflict(run_id,candidate_id) do update set choice=excluded.choice, reason=excluded.reason, updated_at=excluded.updated_at''',(rid,cid,choice,reason,ts,ts))
            # Learn only on first decision; edits are audit data but don't double-count. Production can later support reversible signal deltas.
            if not old: learn_from_decision(con,rid,cid,choice)
            if choice=='yes': con.execute("insert into pipeline(run_id,candidate_id,status,note,updated_at) values(?,?,?,?,?) on conflict(run_id,candidate_id) do nothing",(rid,cid,'Not contacted','',ts))
            else: con.execute('delete from pipeline where run_id=? and candidate_id=?',(rid,cid))
            con.execute('update runs set updated_at=? where id=?',(ts,rid)); log_event(con,rid,'recruiter','CANDIDATE_DECISION',{'candidate_id':cid,'choice':choice,'reason':reason}); con.commit(); con.close(); return self.send_json({'ok':True})
        m=re.fullmatch(r'/api/runs/([^/]+)/pipeline',path)
        if m:
            rid=m.group(1)
            if not self.recruiter_ok(rid,qs): return self.send_json({'error':'unauthorized'},401)
            cid=data.get('candidate_id'); status=data.get('status'); note=clean_text(data.get('note')); allowed=['Not contacted','Contacted','Replied','Screening','Call scheduled','Submitted','Not interested']
            if status not in allowed: return self.send_json({'error':'bad status'},400)
            con=db(); yes=con.execute("select 1 from decisions where run_id=? and candidate_id=? and choice='yes'",(rid,cid)).fetchone()
            if not yes: con.close(); return self.send_json({'error':'candidate not selected'},400)
            con.execute('''insert into pipeline(run_id,candidate_id,status,note,updated_at) values(?,?,?,?,?)
              on conflict(run_id,candidate_id) do update set status=excluded.status,note=excluded.note,updated_at=excluded.updated_at''',(rid,cid,status,note,now())); log_event(con,rid,'recruiter','PIPELINE_UPDATED',{'candidate_id':cid,'status':status}); con.commit(); con.close(); return self.send_json({'ok':True})
        return self.send_error(404)

if __name__=='__main__':
    init_db()
    print(f'Zeli Recruitment V4 running on http://localhost:{PORT}')
    print('Admin dashboard enabled at /admin')
    print('Source adapters:', public_search_provider() or 'public web unconfigured', '| internal pool | GitHub | manual')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
