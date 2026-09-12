#!/usr/bin/env python3
import csv
import gzip
import hashlib
import hmac
import html
import io
import json
import math
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import zlib
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

# Concrete Stack Overflow technology tags only. Generic role words such as
# engineer, software, or developer are never treated as tags by themselves.
STACKEXCHANGE_TAG_SPECS = (
  ('typescript', 'TypeScript', (r'\btypescript\b',)),
  ('javascript', 'JavaScript', (r'\bjavascript\b', r'\bjava[\s-]+script\b')),
  ('python', 'Python', (r'\bpython\b',)),
  ('java', 'Java', (r'\bjava\b',)),
  ('c#', 'C#', (r'(?<!\w)c#(?!\w)', r'\bcsharp\b', r'\bc-sharp\b', r'\bc\s+sharp\b')),
  ('c++', 'C++', (r'(?<!\w)c\+\+(?!\w)', r'\bcpp\b')),
  ('reactjs', 'React', (r'\breactjs\b', r'\breact\.js\b', r'\breact[\s-]+native\b', r'\breact[\s-]+(?:developer|engineer|programmer)\b', r'(?:with|using|in|including|especially)\s+react\b', r'\breact\s+(?:experience|skills?|apps?|components?|framework|library)\b', r'\breact\b(?=\s*[,;/|])')),
  ('node.js', 'Node.js', (r'\bnode\.js\b', r'\bnodejs\b', r'\bnode[\s-]*js\b')),
  ('amazon-web-services', 'AWS', (r'\baws\b', r'\bamazon\s+web\s+services\b')),
  ('azure', 'Azure', (r'\bazure\b',)),
  ('docker', 'Docker', (r'\bdocker\b',)),
  ('kubernetes', 'Kubernetes', (r'\bkubernetes\b', r'\bk8s\b')),
  ('postgresql', 'PostgreSQL', (r'\bpostgresql\b', r'\bpostgres\b')),
  ('mysql', 'MySQL', (r'\bmysql\b',)),
  ('sql', 'SQL', (r'\bsql\b',)),
  ('.net', '.NET', (r'(?<!\w)\.net\b', r'\bdotnet\b', r'\bdot\s*net\b')),
  ('go', 'Go', (r'\bgolang\b', r'\bgo-lang\b', r'\bgo\s+(?:developer|engineer|programmer|language|runtime|backend)\b', r'(?:experience(?:\s+with)?|proficien\w*|skills?|languages?|stack)[^\n.]{0,80}\bgo\b')),
  ('rust', 'Rust', (r'\brust(?:lang|-lang)?\b', r'\brust\s+(?:developer|engineer|programmer|language)\b')),
)
STACKEXCHANGE_MAX_USERS = 30
STACKEXCHANGE_PER_TAG_MIN = 10
STACKEXCHANGE_PER_TAG_MAX = 15

# Research/academic/R&D-only activation. Ordinary commercial titles must self-skip.
OPENALEX_ROLE_PATTERNS = (
  r'\bresearchers?\b',
  r'\bresearch\s+(?:engineer|scientist|fellow|associate|assistant|analyst|director|lead|specialist|intern)\b',
  r'\bscientists?\b',
  r'\bphysicists?\b',
  r'\bchemists?\b',
  r'\bbiologists?\b',
  r'\bprofessors?\b',
  r'\bpost-?docs?\b',
  r'\bpostdoctoral\b',
  r'\bacademic\b',
  r'\bfaculty\b',
  r'\bprincipal\s+investigators?\b',
  r'\bscholars?\b',
  r'\bph\.?d\.?\b',
  r'\bdoctorate\b',
  r'\br(?:\s*&\s*|\s+and\s+)d\b',
  r'\bresearch and development\b',
)
OPENALEX_QUERY_DROP = STOPWORDS | {
  'researcher','researchers','research','scientist','scientists','professor','professors',
  'postdoc','postdocs','postdoctoral','academic','faculty','scholar','scholars',
  'engineer','engineers','engineering','fellow','associate','assistant','director',
  'principal','investigator','investigators','intern','specialist','analyst',
  'phd','doctorate','laboratory','looking','need','needed','focused','focus',
  'someone','including','include','please','seeking'
}
OPENALEX_MAX_AUTHORS = 25
OPENALEX_MAX_WORKS = 20
OPENALEX_AUTHORS_PER_WORK = 4

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
    CREATE TABLE IF NOT EXISTS public_people(
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      title TEXT,
      company TEXT,
      location TEXT,
      profile_url TEXT,
      summary TEXT,
      skills_json TEXT DEFAULT '[]',
      first_seen_at TEXT NOT NULL,
      last_updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_public_people_url on public_people(profile_url) WHERE profile_url IS NOT NULL;
    CREATE TABLE IF NOT EXISTS public_person_sources(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      public_person_id TEXT NOT NULL,
      source_type TEXT NOT NULL,
      source_url TEXT,
      source_provider TEXT,
      snippet TEXT,
      query TEXT,
      discovery_round INTEGER,
      cached_at TEXT NOT NULL,
      FOREIGN KEY(public_person_id) REFERENCES public_people(id) ON DELETE CASCADE
    );
    ''')
    # Backward-compatible run-level sourcing constraints.
    run_cols={row['name'] for row in con.execute('PRAGMA table_info(runs)').fetchall()}
    if 'location' not in run_cols:
        con.execute('ALTER TABLE runs ADD COLUMN location TEXT')
    if 'work_setup' not in run_cols:
        con.execute('ALTER TABLE runs ADD COLUMN work_setup TEXT')
    # Backward-compatible public profile cache columns (kept separate from internal_pool).
    public_people_cols={row['name'] for row in con.execute('PRAGMA table_info(public_people)').fetchall()}
    if 'skills_json' not in public_people_cols:
        con.execute("ALTER TABLE public_people ADD COLUMN skills_json TEXT DEFAULT '[]'")
    if 'summary' not in public_people_cols:
        con.execute('ALTER TABLE public_people ADD COLUMN summary TEXT')
    public_person_sources_cols={row['name'] for row in con.execute('PRAGMA table_info(public_person_sources)').fetchall()}
    if 'source_provider' not in public_person_sources_cols:
        con.execute('ALTER TABLE public_person_sources ADD COLUMN source_provider TEXT')
    if 'discovery_round' not in public_person_sources_cols:
        con.execute('ALTER TABLE public_person_sources ADD COLUMN discovery_round INTEGER')
    # Backward-compatible geography eligibility columns. Scoring stays separate.
    cand_cols={row['name'] for row in con.execute('PRAGMA table_info(candidates)').fetchall()}
    if 'geo_status' not in cand_cols:
        con.execute("ALTER TABLE candidates ADD COLUMN geo_status TEXT DEFAULT 'UNKNOWN'")
    if 'geo_evidence' not in cand_cols:
        con.execute('ALTER TABLE candidates ADD COLUMN geo_evidence TEXT')
    if 'geo_reason' not in cand_cols:
        con.execute('ALTER TABLE candidates ADD COLUMN geo_reason TEXT')
    if 'geo_override' not in cand_cols:
        con.execute('ALTER TABLE candidates ADD COLUMN geo_override INTEGER NOT NULL DEFAULT 0')
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

def fold_geo(text):
    text=unicodedata.normalize('NFD', text or '')
    text=''.join(ch for ch in text if unicodedata.category(ch)!='Mn')
    text=text.replace('&',' and ').replace('/',' ').replace('-',' ')
    text=re.sub(r'[^\w\s,.]',' ', text.lower())
    return re.sub(r'\s+',' ', text).strip()

# Latin America and generic country/region gazetteer. Only explicit public location
# strings are parsed; names, companies, schools and language are never used.
LATAM_COUNTRIES = {
  'AR','BO','BR','CL','CO','CR','CU','DO','EC','SV','GT','HN','MX','NI','PA','PY','PE','PR','UY','VE','BZ','GY','SR','GF'
}
SOUTH_AMERICA_COUNTRIES = {'AR','BO','BR','CL','CO','EC','GY','PY','PE','SR','UY','VE','GF'}
NORTH_AMERICA_COUNTRIES = {'US','CA','MX'}
EUROPE_COUNTRIES = {'GB','IE','FR','DE','ES','IT','PT','NL','BE','SE','NO','FI','DK','AT','CH','PL'}

COUNTRY_ALIASES = {
  'argentina':'AR','ar':'AR',
  'bolivia':'BO','bo':'BO',
  'brazil':'BR','brasil':'BR','br':'BR',
  'chile':'CL','cl':'CL',
  'colombia':'CO',
  'costa rica':'CR','cr':'CR',
  'cuba':'CU','cu':'CU',
  'dominican republic':'DO','republica dominicana':'DO','do':'DO',
  'ecuador':'EC','ec':'EC',
  'el salvador':'SV','sv':'SV',
  'guatemala':'GT','gt':'GT',
  'honduras':'HN','hn':'HN',
  'mexico':'MX','mx':'MX',
  'nicaragua':'NI','ni':'NI',
  'panama':'PA',
  'paraguay':'PY','py':'PY',
  'peru':'PE','pe':'PE',
  'puerto rico':'PR','pr':'PR',
  'uruguay':'UY','uy':'UY',
  'venezuela':'VE','ve':'VE',
  'belize':'BZ','bz':'BZ',
  'guyana':'GY','gy':'GY',
  'suriname':'SR','sr':'SR',
  'french guiana':'GF','guiana':'GF','gf':'GF',
  'united states':'US','united states of america':'US','usa':'US','u.s.':'US','u.s.a.':'US','us':'US',
  'united kingdom':'GB','uk':'GB','great britain':'GB','britain':'GB','england':'GB','scotland':'GB','wales':'GB','gb':'GB',
  'india':'IN',
  'germany':'DE','deutschland':'DE','de':'DE',
  'france':'FR','fr':'FR',
  'canada':'CA','ca':'CA',
  'spain':'ES','espana':'ES','es':'ES',
  'italy':'IT','italia':'IT','it':'IT',
  'australia':'AU','au':'AU',
  'japan':'JP','jp':'JP',
  'china':'CN','cn':'CN',
  'netherlands':'NL','holland':'NL','nl':'NL',
  'portugal':'PT','pt':'PT',
  'ireland':'IE','ie':'IE',
  'switzerland':'CH','ch':'CH',
  'austria':'AT','at':'AT',
  'belgium':'BE','be':'BE',
  'sweden':'SE','se':'SE',
  'norway':'NO','no':'NO',
  'denmark':'DK','dk':'DK',
  'finland':'FI','fi':'FI',
  'poland':'PL','pl':'PL',
  'new zealand':'NZ','nz':'NZ',
  'south africa':'ZA','za':'ZA',
  'singapore':'SG','sg':'SG',
}
COUNTRY_LABELS = {
  'AR':'Argentina','BO':'Bolivia','BR':'Brazil','CL':'Chile','CO':'Colombia','CR':'Costa Rica','CU':'Cuba',
  'DO':'Dominican Republic','EC':'Ecuador','SV':'El Salvador','GT':'Guatemala','HN':'Honduras','MX':'Mexico',
  'NI':'Nicaragua','PA':'Panama','PY':'Paraguay','PE':'Peru','PR':'Puerto Rico','UY':'Uruguay','VE':'Venezuela',
  'BZ':'Belize','GY':'Guyana','SR':'Suriname','GF':'French Guiana','US':'USA','GB':'United Kingdom','IN':'India',
  'DE':'Germany','FR':'France','CA':'Canada','ES':'Spain','IT':'Italy','AU':'Australia','JP':'Japan','CN':'China',
  'NL':'Netherlands','PT':'Portugal','IE':'Ireland','CH':'Switzerland','AT':'Austria','BE':'Belgium','SE':'Sweden',
  'NO':'Norway','DK':'Denmark','FI':'Finland','PL':'Poland','NZ':'New Zealand','ZA':'South Africa','SG':'Singapore'
}
# Whole-string ISO codes, including codes that collide with US state abbreviations
# when they appear inside a longer city/state string.
ISO_WHOLE_COUNTRIES = {k.upper():v for k,v in COUNTRY_ALIASES.items() if len(k)==2 and k.isalpha()}
ISO_WHOLE_COUNTRIES.update({'IN':'IN','CO':'CO','PA':'PA','UK':'GB'})

US_STATES = {
  'alabama':'alabama','al':'alabama','alaska':'alaska','ak':'alaska','arizona':'arizona','az':'arizona',
  'arkansas':'arkansas','california':'california','ca':'california','colorado':'colorado',
  'connecticut':'connecticut','ct':'connecticut','delaware':'delaware','florida':'florida','fl':'florida',
  'georgia':'georgia','hawaii':'hawaii','hi':'hawaii','idaho':'idaho','illinois':'illinois','il':'illinois',
  'indiana':'indiana','iowa':'iowa','ia':'iowa','kansas':'kansas','ks':'kansas','kentucky':'kentucky','ky':'kentucky',
  'louisiana':'louisiana','la':'louisiana','maine':'maine','me':'maine','maryland':'maryland','md':'maryland',
  'massachusetts':'massachusetts','ma':'massachusetts','michigan':'michigan','mi':'michigan',
  'minnesota':'minnesota','mn':'minnesota','mississippi':'mississippi','ms':'mississippi',
  'missouri':'missouri','mo':'missouri','montana':'montana','mt':'montana','nebraska':'nebraska','ne':'nebraska',
  'nevada':'nevada','nv':'nevada','new hampshire':'new hampshire','nh':'new hampshire',
  'new jersey':'new jersey','nj':'new jersey','new mexico':'new mexico','nm':'new mexico',
  'new york':'new york','ny':'new york','north carolina':'north carolina','nc':'north carolina',
  'north dakota':'north dakota','nd':'north dakota','ohio':'ohio','oh':'ohio','oklahoma':'oklahoma','ok':'oklahoma',
  'oregon':'oregon','or':'oregon','pennsylvania':'pennsylvania','rhode island':'rhode island','ri':'rhode island',
  'south carolina':'south carolina','sc':'south carolina','south dakota':'south dakota','sd':'south dakota',
  'tennessee':'tennessee','tn':'tennessee','texas':'texas','tx':'texas','utah':'utah','ut':'utah',
  'vermont':'vermont','vt':'vermont','virginia':'virginia','va':'virginia','washington':'washington','wa':'washington',
  'west virginia':'west virginia','wv':'west virginia','wisconsin':'wisconsin','wi':'wisconsin',
  'wyoming':'wyoming','wy':'wyoming','district of columbia':'district of columbia','washington dc':'district of columbia','dc':'district of columbia'
}
# City → (country, admin_or_None, display, needs_disambiguator_or_None)
GEO_CITIES = {
  'bogota':('CO',None,'Bogotá',None),'medellin':('CO',None,'Medellín',None),'cali':('CO',None,'Cali',None),
  'cartagena':('CO',None,'Cartagena',None),'barranquilla':('CO',None,'Barranquilla',None),
  'sao paulo':('BR',None,'São Paulo',None),'rio de janeiro':('BR',None,'Rio de Janeiro',None),
  'brasilia':('BR',None,'Brasília',None),'belo horizonte':('BR',None,'Belo Horizonte',None),
  'buenos aires':('AR',None,'Buenos Aires',None),
  'lima':('PE',None,'Lima',None),'quito':('EC',None,'Quito',None),'guayaquil':('EC',None,'Guayaquil',None),
  'caracas':('VE',None,'Caracas',None),'montevideo':('UY',None,'Montevideo',None),
  'asuncion':('PY',None,'Asunción',None),'la paz':('BO',None,'La Paz',None),
  'mexico city':('MX',None,'Mexico City',None),'ciudad de mexico':('MX',None,'Mexico City',None),'cdmx':('MX',None,'Mexico City',None),
  'guadalajara':('MX',None,'Guadalajara',None),'monterrey':('MX',None,'Monterrey',None),
  'santo domingo':('DO',None,'Santo Domingo',None),'havana':('CU',None,'Havana',None),'habana':('CU',None,'Havana',None),
  'san salvador':('SV',None,'San Salvador',None),'guatemala city':('GT',None,'Guatemala City',None),
  'tegucigalpa':('HN',None,'Tegucigalpa',None),'managua':('NI',None,'Managua',None),
  'cincinnati':('US','ohio','Cincinnati',None),'nashville':('US','tennessee','Nashville',None),
  'bengaluru':('IN',None,'Bengaluru',None),'bangalore':('IN',None,'Bengaluru',None),
  'berlin':('DE',None,'Berlin',None),'munich':('DE',None,'Munich',None),'paris':('FR',None,'Paris',None),
  'toronto':('CA',None,'Toronto',None),'sydney':('AU',None,'Sydney',None),
}
AMBIGUOUS_CITIES = {
  'london':(('GB',None,'London',('uk','united kingdom','england','britain','gb')),('CA','ontario','London',('canada','ontario','ca'))),
  'birmingham':(('US','alabama','Birmingham',('alabama','al','usa','united states','us')),('GB',None,'Birmingham',('uk','united kingdom','england','britain','gb'))),
  'panama city':(('PA',None,'Panama City',('panama','pa','latam','latin america')),('US','florida','Panama City',('florida','fl','usa','united states','us'))),
  'san jose':(('CR',None,'San José',('costa rica','cr','latam','latin america')),('US','california','San Jose',('california','ca','usa','united states','us'))),
  'santiago':(('CL',None,'Santiago',('chile','cl','latam','latin america')),),
}

REGION_ALIASES = {
  'latin america':'latin_america','latam':'latin_america','latinoamerica':'latin_america',
  'latino america':'latin_america','america latina':'latin_america','latin-america':'latin_america',
  'south america':'south_america','southamerica':'south_america',
  'north america':'north_america','northamerica':'north_america',
  'europe':'europe','eu':'europe',
  'worldwide':'worldwide','world wide':'worldwide','global':'worldwide','anywhere':'worldwide','world':'worldwide',
}
REGION_COUNTRIES = {
  'latin_america':LATAM_COUNTRIES,
  'south_america':SOUTH_AMERICA_COUNTRIES,
  'north_america':NORTH_AMERICA_COUNTRIES,
  'europe':EUROPE_COUNTRIES,
}
REGION_LABELS = {
  'latin_america':'Latin America','south_america':'South America','north_america':'North America','europe':'Europe','worldwide':'Worldwide'
}

def _geo_blank():
    return {'kind':None,'region':None,'country':None,'admin':None,'city':None,'city_label':None,'admin_label':None,'label':'','raw':'','ambiguous':False}

def parse_geo(text):
    raw=clean_text(text)
    out=_geo_blank(); out['raw']=raw
    folded=fold_geo(raw)
    if not folded: return out
    compact=re.sub(r'[^\w]+','',folded)
    if folded in REGION_ALIASES or compact in {'latam','worldwide','global'}:
        region=REGION_ALIASES.get(folded) or ('latin_america' if compact=='latam' else 'worldwide')
        out.update(kind='worldwide' if region=='worldwide' else 'region', region=region, label=REGION_LABELS.get(region,raw))
        return out
    if re.fullmatch(r'[a-z]{2}', folded):
        code=ISO_WHOLE_COUNTRIES.get(folded.upper())
        if code:
            out.update(kind='country', country=code, label=COUNTRY_LABELS.get(code,code))
            return out
        out['ambiguous']=True
        return out
    # Longest city / country / state matches on the folded string.
    found_city=None
    for name in sorted(list(GEO_CITIES)+list(AMBIGUOUS_CITIES), key=len, reverse=True):
        if re.search(r'(^|[\s,.])'+re.escape(name)+r'($|[\s,.])', folded):
            found_city=name; break
    if found_city in AMBIGUOUS_CITIES:
        options=AMBIGUOUS_CITIES[found_city]
        matched=None
        for country,admin,label,hints in options:
            if hints and any(re.search(r'(^|[\s,.])'+re.escape(h)+r'($|[\s,.])', folded) for h in hints):
                matched=(country,admin,label); break
        if matched:
            country,admin,label=matched
            out.update(kind='city', country=country, admin=admin, city=found_city, city_label=label, admin_label=admin.title() if admin else None, label=label)
        else:
            out['ambiguous']=True
            out['label']=raw
            return out
    elif found_city:
        country,admin,label,_=GEO_CITIES[found_city]
        out.update(kind='city', country=country, admin=admin, city=found_city, city_label=label, admin_label=admin.title() if admin else None, label=label)
    found_country=None
    for name in sorted(COUNTRY_ALIASES, key=len, reverse=True):
        if len(name)<3 and name not in {'usa','uk'}: continue
        if re.search(r'(^|[\s,.])'+re.escape(name)+r'($|[\s,.])', folded):
            found_country=COUNTRY_ALIASES[name]; break
    if found_country:
        out['country']=out['country'] or found_country
        if not out['kind']:
            out.update(kind='country', label=COUNTRY_LABELS.get(found_country,raw))
    found_admin=None
    for name in sorted(US_STATES, key=len, reverse=True):
        if len(name)==2 and not re.search(r'(^|[\s,.])'+re.escape(name)+r'($|[\s,.])', folded):
            continue
        if re.search(r'(^|[\s,.])'+re.escape(name)+r'($|[\s,.])', folded):
            found_admin=US_STATES[name]; break
    if found_admin:
        out['admin']=out['admin'] or found_admin
        out['admin_label']=found_admin.title()
        out['country']=out['country'] or 'US'
        if out['kind'] not in ('city',):
            out.update(kind='admin', label=found_admin.title()+', USA')
    if out['country'] and not out['label']:
        out['label']=COUNTRY_LABELS.get(out['country'], raw)
    if not out['kind'] and not out['ambiguous']:
        # Unresolved free text is unknown, not a guessed place.
        out['ambiguous']=True
        out['label']=raw
    return out

def evaluate_geography(required_location, candidate_location):
    # Eligibility only. Uses explicit candidate location text; never name/company/school.
    req=parse_geo(required_location)
    evidence=clean_text(candidate_location)
    if not req.get('kind') or req.get('kind')=='worldwide' or req.get('region')=='worldwide':
        return {'status':'MET','evidence':evidence,'reason':'Worldwide / unrestricted geography'}
    if not evidence:
        return {'status':'UNKNOWN','evidence':'','reason':'No reliable candidate location'}
    cand=parse_geo(candidate_location)
    if cand.get('ambiguous') and not cand.get('country') and not cand.get('city') and not cand.get('region'):
        return {'status':'UNKNOWN','evidence':evidence,'reason':f'{evidence} is ambiguous'}
    req_label=req.get('label') or clean_text(required_location)
    cand_label=cand.get('city_label') or cand.get('label') or evidence

    def not_met(detail):
        return {'status':'NOT_MET','evidence':evidence,'reason':detail}

    def met(detail):
        return {'status':'MET','evidence':evidence,'reason':detail}

    def unknown(detail):
        return {'status':'UNKNOWN','evidence':evidence,'reason':detail}

    if req.get('city'):
        if cand.get('city') and cand.get('city')==req['city'] and (not req.get('country') or cand.get('country')==req.get('country')):
            return met(f"{cand_label} matches {req_label}")
        if cand.get('country') and req.get('country') and cand['country']!=req['country']:
            return not_met(f"{cand_label} is outside {req_label}")
        if cand.get('admin') and req.get('admin') and cand['admin']!=req['admin'] and cand.get('country')==req.get('country'):
            return not_met(f"{cand_label} is outside {req_label}")
        if cand.get('city') and req.get('country') and cand.get('country')==req.get('country') and cand.get('city')!=req.get('city'):
            return not_met(f"{cand_label} is outside {req_label}")
        if cand.get('country')==req.get('country') and not cand.get('city'):
            return unknown(f"{evidence} is not specific enough for {req_label}")
        return unknown(f"{evidence} is not specific enough for {req_label}")

    if req.get('admin'):
        if cand.get('admin')==req.get('admin') and (not req.get('country') or cand.get('country')==req.get('country')):
            return met(f"{cand_label} is in {req_label}")
        if cand.get('country') and req.get('country') and cand['country']!=req['country']:
            return not_met(f"{cand_label} is outside {req_label}")
        if cand.get('admin') and cand['admin']!=req['admin']:
            return not_met(f"{cand_label} is outside {req_label}")
        if cand.get('country')==req.get('country') and not cand.get('admin'):
            return unknown(f"{evidence} is not specific enough for {req_label}")
        return unknown(f"{evidence} is not specific enough for {req_label}")

    if req.get('country') and not req.get('region'):
        if cand.get('country')==req.get('country'):
            return met(f"{cand_label} is in {req_label}")
        if cand.get('country') and cand['country']!=req['country']:
            return not_met(f"{cand_label} is outside {req_label}")
        if cand.get('region') and req['country'] in REGION_COUNTRIES.get(cand['region'], set()):
            return unknown(f"{evidence} is not specific enough for {req_label}")
        return unknown(f"{evidence} is not specific enough for {req_label}")

    if req.get('region'):
        allowed=REGION_COUNTRIES.get(req['region'], set())
        if cand.get('country') and cand['country'] in allowed:
            return met(f"{cand_label} is in {req_label}")
        if cand.get('region')==req['region']:
            return met(f"{cand_label} is in {req_label}")
        if cand.get('region') and cand['region']!=req['region']:
            extra=REGION_COUNTRIES.get(cand['region'], set())
            if extra and extra<=allowed:
                return met(f"{cand_label} is in {req_label}")
            if extra and extra.isdisjoint(allowed):
                return not_met(f"{cand_label} is outside {req_label}")
            return unknown(f"{evidence} is not specific enough for {req_label}")
        if cand.get('country') and cand['country'] not in allowed:
            return not_met(f"{cand_label} is outside {req_label}")
        return unknown(f"{evidence} is not specific enough for {req_label}")

    return unknown(f"{evidence} is not specific enough for {req_label}")

def candidate_geo_eval(run, location):
    required=''
    if run is not None:
        try: required=clean_text(run['location'] or '')
        except Exception: required=clean_text(getattr(run,'location','') or '')
    return evaluate_geography(required, location)

def apply_geo_ranking(con, run_id):
    rows=con.execute('select id,score,coalesce(geo_status,\'UNKNOWN\') geo_status from candidates where run_id=?',(run_id,)).fetchall()
    rank_key={'MET':0,'UNKNOWN':1,'NOT_MET':2}
    ordered=sorted(rows, key=lambda r:(rank_key.get(r['geo_status'],1), -(r['score'] or 0), r['id']))
    for i,row in enumerate(ordered, start=1):
        con.execute('update candidates set rank_order=? where id=?',(i,row['id']))

def geo_publishable(row):
    status=(row['geo_status'] if 'geo_status' in row.keys() else None) or 'UNKNOWN'
    override=int(row['geo_override'] if 'geo_override' in row.keys() and row['geo_override'] is not None else 0)
    return status!='NOT_MET' or override==1

def apply_operator_approve(con, candidate, confirm_geo_override=False):
    # MET / UNKNOWN use the normal approve path. NOT_MET stays unapproved unless
    # the operator explicitly confirms a geography override.
    geo_st=(candidate['geo_status'] if 'geo_status' in candidate.keys() else None) or 'UNKNOWN'
    reason=(candidate['geo_reason'] if 'geo_reason' in candidate.keys() else None) or ''
    if geo_st=='NOT_MET' and not confirm_geo_override:
        return {'ok':False,'needs_geo_override':True,'geo_status':'NOT_MET','geo_reason':reason}
    if geo_st=='NOT_MET':
        con.execute("update candidates set operator_status='APPROVED',geo_override=1,updated_at=? where id=?",(now(),candidate['id']))
    else:
        con.execute("update candidates set operator_status='APPROVED',updated_at=? where id=?",(now(),candidate['id']))
    return {'ok':True}

def github_location_query(location_hint):
    # Only pass a GitHub location: target when the place is specific enough.
    g=parse_geo(location_hint)
    if not g.get('kind') or g['kind'] in ('worldwide','region'):
        return ''
    if g.get('city_label'): return g['city_label']
    if g.get('admin_label') and g.get('country')=='US': return g['admin_label']
    if g.get('country'): return COUNTRY_LABELS.get(g['country'],'')
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
    geo=parse_geo(location)
    return {'rounds':rounds,'profile_locator_queries':locator,'location_hint':location,'work_setup':work_setup,
      'geography':{'raw':location,'kind':geo.get('kind'),'region':geo.get('region'),'country':geo.get('country'),
        'admin':geo.get('admin'),'city':geo.get('city'),'label':geo.get('label')}}

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
    cache_count=con.execute('select count(*) n from public_people').fetchone()['n']
    out={
      'public_cache':{'available':cache_count>0,'records':cache_count,'description':'Cached public discoveries reused before live API calls'},
      'internal_pool':{'available':count>0,'records':count,'description':'Recruiter-owned candidate records / CSV'},
      'public_web':{'available':bool(provider),'provider':provider,'description':'Search-engine/API discovery across the public web'},
      'github':{'available':True,'authenticated':bool(os.getenv('GITHUB_TOKEN')),'description':'Optional technical-talent signal source'},
      'stackexchange':{'available':True,'key_configured':bool(os.getenv('STACKEXCHANGE_KEY')),'description':'Official Stack Exchange API v2.3; available without a key'},
      'openalex':{'available':True,'key_configured':bool(os.getenv('OPENALEX_API_KEY')),'description':'Official OpenAlex API; available without a key'},
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

# ---------------- public profile cache (public_web / github / stackexchange / openalex reuse) ----------------
# This cache is intentionally separate from internal_pool: internal_pool is recruiter-owned
# private data, while public_people only stores what was already discovered from public
# sources (public_web, github, stackexchange, openalex) so future runs can reuse it instead of re-querying providers.
def public_graph_search(con,query,limit=10):
    rows=con.execute('select * from public_people where profile_url is not null and profile_url<>\'\'').fetchall()
    q=set(tokens(query))
    scored=[]
    for r in rows:
        text=' '.join([r['name'],r['title'] or '',r['company'] or '',r['location'] or '',r['summary'] or '',' '.join(jload(r['skills_json'],[]) or [])])
        tt=set(tokens(text))
        overlap=len(q & tt)
        phrase_bonus=2 if clean_text(query).lower() in text.lower() else 0
        s=overlap+phrase_bonus
        if s>0: scored.append((s,r))
    scored.sort(key=lambda x:(x[0],x[1]['last_updated_at']),reverse=True)
    hits=[]
    for score,r in scored[:limit]:
        hits.append({
          'name':r['name'],'title':r['title'] or '','company':r['company'] or '','location':r['location'] or '',
          'profile_url':r['profile_url'] or '','summary':r['summary'] or '','skills':jload(r['skills_json'],[]) or [],
          'source_type':'public_cache','source_url':r['profile_url'] or '',
          'source_title':f"{r['name']} · Public profile cache",
          'snippet':r['summary'] or 'Cached from a previous public discovery','query':query,'discovery_score':score
        })
    return hits

def upsert_public_person(con,hit,source_type,source_url,source_provider='',query='',discovery_round=1):
    # Only public_web / github / stackexchange / openalex discoveries are eligible for
    # caching; internal_pool must never be written here.
    if source_type not in ('public_web','github','stackexchange','openalex'): return None
    url=clean_text(hit.get('profile_url',''))
    if not url: return None
    pid=canonical_key(hit)
    ts=now()
    skills=hit.get('skills') or []
    con.execute('''insert into public_people(id,name,title,company,location,profile_url,summary,skills_json,first_seen_at,last_updated_at)
      values(?,?,?,?,?,?,?,?,?,?)
      on conflict(id) do update set
      name=excluded.name,
      title=coalesce(nullif(excluded.title,\'\'),public_people.title),
      company=coalesce(nullif(excluded.company,\'\'),public_people.company),
      location=coalesce(nullif(excluded.location,\'\'),public_people.location),
      profile_url=excluded.profile_url,
      summary=coalesce(nullif(excluded.summary,\'\'),public_people.summary),
      skills_json=excluded.skills_json,
      last_updated_at=excluded.last_updated_at''',
      (pid,clean_text(hit.get('name','')) or 'Public web result',clean_text(hit.get('title','')),clean_text(hit.get('company','')),
       clean_text(hit.get('location','')),url,clean_text(hit.get('summary','')),jdump(skills),ts,ts))
    src_url=clean_text(source_url or hit.get('source_url',''))
    exists=con.execute('select 1 from public_person_sources where public_person_id=? and source_type=? and coalesce(source_url,\'\')=?',
      (pid,source_type,src_url)).fetchone()
    if not exists:
        con.execute('''insert into public_person_sources(public_person_id,source_type,source_url,source_provider,snippet,query,discovery_round,cached_at)
          values(?,?,?,?,?,?,?,?)''',
          (pid,source_type,src_url,clean_text(source_provider),clean_text(hit.get('snippet',''))[:2500],clean_text(query)[:1000],discovery_round,ts))
    return pid

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
    gh_loc=github_location_query(location_hint)
    if gh_loc:
        gh_query += f' location:"{gh_loc}"'
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

def extract_stackexchange_tags(*parts):
    # Only concrete technology names become tags. engineer/software/developer never qualify alone.
    text=clean_text(' '.join(p for p in parts if p))
    if not text: return []
    text_l=text.lower()
    found=[]
    for so_tag,label,pats in STACKEXCHANGE_TAG_SPECS:
        pos=None
        for pat in pats:
            m=re.search(pat,text_l)
            if m:
                pos=m.start(); break
        if pos is not None:
            found.append((pos,so_tag,label))
    tags={t for _,t,_ in found}
    if 'reactjs' not in tags:
        m=re.search(r'\breact\b',text_l)
        if m and tags:
            found.append((m.start(),'reactjs','React'))
    if 'go' not in tags:
        m=re.search(r'(?:^|[\s,;/|(])go(?=[\s,;/|)]|$)',text_l)
        if m and tags:
            found.append((m.start(),'go','Go'))
    found.sort(key=lambda x:x[0])
    out=[]; seen=set()
    for _,so_tag,label in found:
        if so_tag in seen: continue
        seen.add(so_tag)
        out.append({'tag':so_tag,'label':label})
    return out

def _inflate_stackexchange_body(raw, content_encoding=''):
    if not raw: return raw
    enc=(content_encoding or '').lower()
    if raw[:1] in (b'{', b'['): return raw
    if 'deflate' in enc and 'gzip' not in enc:
        return zlib.decompress(raw)
    try:
        return gzip.decompress(raw)
    except Exception:
        try:
            return zlib.decompress(raw)
        except Exception:
            return raw

def stackexchange_request(path, params=None):
    params=dict(params or {})
    params.setdefault('site','stackoverflow')
    key=os.getenv('STACKEXCHANGE_KEY')
    if key: params['key']=key
    url='https://api.stackexchange.com/2.3/'+path.lstrip('/')
    if params: url+='?'+urlencode(params, doseq=True)
    req=Request(url,method='GET',headers={'User-Agent':USER_AGENT,'Accept':'application/json','Accept-Encoding':'gzip, deflate'})
    try:
        with urlopen(req,timeout=PUBLIC_SEARCH_TIMEOUT) as resp:
            raw=_inflate_stackexchange_body(resp.read(), resp.headers.get('Content-Encoding',''))
            data=json.loads(raw.decode('utf-8','replace'))
    except HTTPError as e:
        raw=_inflate_stackexchange_body(e.read(), e.headers.get('Content-Encoding','') if e.headers else '')
        try:
            data=json.loads(raw.decode('utf-8','replace'))
        except Exception:
            raise RuntimeError(f'Stack Exchange HTTP {e.code}') from e
    if not isinstance(data,dict):
        raise RuntimeError('Stack Exchange returned an unexpected payload')
    return data

def _stackexchange_user_hit(user, tags, answer_score, query):
    name=html.unescape(clean_text(user.get('display_name') or ''))
    if not name: return None
    uid=user.get('user_id')
    profile=clean_text(user.get('link') or '') or (f'https://stackoverflow.com/users/{uid}' if uid else '')
    location=html.unescape(clean_text(user.get('location') or ''))
    website=clean_text(user.get('website_url') or '')
    reputation=user.get('reputation')
    labels=[t['label'] for t in tags]
    bits=[]
    if labels: bits.append('Top answerer for '+', '.join(labels))
    if reputation not in (None,''): bits.append(f'Reputation: {reputation}')
    if answer_score not in (None,''): bits.append(f'Answer score: {answer_score}')
    if website: bits.append(f'Website: {website}')
    summary=clean_text('. '.join(bits)+('.' if bits else ''))
    return {
      'name':name,
      'title':'Stack Overflow contributor',
      'company':'',
      'location':location,
      'profile_url':profile,
      'summary':summary,
      'skills':labels,
      'source_type':'stackexchange',
      'source_url':profile,
      'source_title':f'{name} on Stack Overflow',
      'snippet':summary,
      'query':query
    }

def stackexchange_search(query, source_text='', state=None, per_tag_limit=12, max_users=STACKEXCHANGE_MAX_USERS):
    # Technical-only adapter: self-skips with 0 hits when no concrete technology tags are present.
    state=state if isinstance(state,dict) else {}
    if state.get('backoff'): return []
    tags=extract_stackexchange_tags(source_text or query)
    if not tags: return []
    pending=[t for t in tags if t['tag'] not in (state.get('fetched_tags') or set())]
    if not pending: return []
    per_tag=bounded(int(per_tag_limit or 12), STACKEXCHANGE_PER_TAG_MIN, STACKEXCHANGE_PER_TAG_MAX)
    max_users=bounded(int(max_users or STACKEXCHANGE_MAX_USERS), 1, STACKEXCHANGE_MAX_USERS)
    collected=state.setdefault('users', {})
    fetched=state.setdefault('fetched_tags', set())
    returned=state.setdefault('returned_ids', set())

    def mark_backoff(data):
        if not data: return False
        err=str(data.get('error_name') or '').lower()
        if data.get('backoff') or data.get('quota_remaining')==0 or 'throttle' in err:
            state['backoff']=True
            return True
        return False

    for spec in pending:
        if state.get('backoff'): break
        path='tags/'+quote(spec['tag'], safe='')+'/top-answerers/all_time'
        data=stackexchange_request(path, {'pagesize':per_tag})
        fetched.add(spec['tag'])
        stopped=mark_backoff(data)
        if data.get('error_id') and not data.get('items'):
            if stopped: break
            raise RuntimeError(data.get('error_message') or f"Stack Exchange error for tag {spec['tag']}")
        for item in (data.get('items') or [])[:per_tag]:
            user=(item or {}).get('user') or {}
            uid=user.get('user_id')
            if not uid: continue
            if uid in collected:
                if spec not in collected[uid]['tags']:
                    collected[uid]['tags'].append(spec)
                if (item.get('score') or 0)>(collected[uid].get('score') or 0):
                    collected[uid]['score']=item.get('score')
                    collected[uid]['user']={**collected[uid]['user'], **{k:v for k,v in user.items() if v}}
                continue
            if len(collected)>=max_users: continue
            collected[uid]={'user':user,'score':item.get('score'),'tags':[spec]}
        if stopped or len(collected)>=max_users: break

    if not collected: return []
    if not state.get('backoff'):
        ids=[str(uid) for uid in collected.keys()]
        try:
            data=stackexchange_request('users/'+';'.join(ids), {'pagesize':len(ids)})
            mark_backoff(data)
            if data.get('error_id') and not data.get('items'):
                if not state.get('backoff'):
                    raise RuntimeError(data.get('error_message') or 'Stack Exchange user lookup failed')
            else:
                by_id={u.get('user_id'):u for u in (data.get('items') or []) if u.get('user_id')}
                for uid,row in collected.items():
                    extra=by_id.get(uid)
                    if extra: row['user']={**row['user'], **extra}
        except Exception:
            # Keep conservative shallow-user records rather than failing the run.
            pass
    hits=[]
    for uid,row in collected.items():
        if uid in returned: continue
        hit=_stackexchange_user_hit(row['user'], row['tags'], row.get('score'), query)
        if hit:
            returned.add(uid)
            hits.append(hit)
    return hits

def is_openalex_research_role(*parts):
    text=clean_text(' '.join(p for p in parts if p)).lower()
    if not text: return False
    return any(re.search(p,text) for p in OPENALEX_ROLE_PATTERNS)

def build_openalex_topic_query(*parts):
    # Compact topical search for /works. Do not use job titles as an author-name query.
    text=clean_text(' '.join(p for p in parts if p))
    if not text: return ''
    kept=[]
    for t in tokens(text):
        if t in OPENALEX_QUERY_DROP: continue
        if t not in kept: kept.append(t)
        if len(kept)>=8: break
    return ' '.join(kept[:6])

def openalex_request(path, params=None):
    params=dict(params or {})
    key=os.getenv('OPENALEX_API_KEY')
    if key: params['api_key']=key
    url='https://api.openalex.org/'+path.lstrip('/')
    if params: url+='?'+urlencode(params, doseq=True)
    req=Request(url,method='GET',headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    try:
        with urlopen(req,timeout=PUBLIC_SEARCH_TIMEOUT) as resp:
            data=json.loads(resp.read().decode('utf-8','replace'))
    except HTTPError as e:
        raw=e.read() if e.fp else b''
        try:
            data=json.loads(raw.decode('utf-8','replace'))
        except Exception:
            data={'error':f'OpenAlex HTTP {e.code}'}
        if e.code==429:
            data=data if isinstance(data,dict) else {}
            data['_backoff']=True
            return data
        raise RuntimeError(data.get('error') or data.get('message') or f'OpenAlex HTTP {e.code}') from e
    if not isinstance(data,dict):
        raise RuntimeError('OpenAlex returned an unexpected payload')
    return data

def _openalex_author_id(author):
    raw=clean_text((author or {}).get('id') or '')
    if not raw: return ''
    if raw.startswith('https://openalex.org/'): return raw.rsplit('/',1)[-1]
    if re.fullmatch(r'A\d+', raw): return raw
    return ''

def _openalex_pick_authors(work):
    authorships=list(work.get('authorships') or [])
    ordered=[]
    seen=set()
    for pool in (
      [a for a in authorships if a.get('is_corresponding')],
      [a for a in authorships if a.get('author_position')=='first'],
      authorships
    ):
        for a in pool:
            aid=_openalex_author_id((a or {}).get('author') or {})
            key=aid or clean_text(((a or {}).get('author') or {}).get('display_name') or '').lower()
            if not key or key in seen: continue
            seen.add(key)
            ordered.append(a)
            if len(ordered)>=OPENALEX_AUTHORS_PER_WORK: return ordered
    return ordered

def _openalex_institution(inst):
    if not isinstance(inst,dict): return '',''
    name=clean_text(inst.get('display_name') or '')
    loc=clean_text(inst.get('country_code') or '')
    return name,loc

def _openalex_skill_terms(works, author_topics=None):
    terms=[]
    def add(name):
        name=clean_text(name)
        if name and name.lower() not in {t.lower() for t in terms}:
            terms.append(name)
    for w in works or []:
        pt=(w or {}).get('primary_topic') or {}
        add(pt.get('display_name'))
        for t in ((w or {}).get('topics') or [])[:3]:
            add((t or {}).get('display_name'))
    for t in (author_topics or [])[:4]:
        add((t or {}).get('display_name'))
    return terms[:8]

def _openalex_author_hit(row, query):
    author=row.get('author') or {}
    name=clean_text(author.get('display_name') or '')
    if not name: return None
    aid=_openalex_author_id(author)
    profile=clean_text(author.get('id') or '') or (f'https://openalex.org/{aid}' if aid else '')
    inst_name,inst_loc=row.get('institution_name') or '', row.get('institution_location') or ''
    works=row.get('works') or []
    titles=[clean_text(w.get('display_name') or '') for w in works if clean_text(w.get('display_name') or '')]
    cited=sum(int(w.get('cited_by_count') or 0) for w in works)
    skills=_openalex_skill_terms(works, (row.get('hydrated') or {}).get('topics'))
    bits=[]
    if titles:
        shown=', '.join(titles[:2])
        extra=f' (+{len(titles)-2} more)' if len(titles)>2 else ''
        bits.append(f'Author of {len(titles)} relevant work{"s" if len(titles)!=1 else ""} including {shown}{extra}')
    if skills: bits.append('Topics: '+', '.join(skills[:4]))
    if cited: bits.append(f'Citations on matched works: {cited}')
    wc=(row.get('hydrated') or {}).get('works_count')
    cc=(row.get('hydrated') or {}).get('cited_by_count')
    if wc not in (None,''): bits.append(f'OpenAlex works: {wc}')
    if cc not in (None,'') and not cited: bits.append(f'OpenAlex citations: {cc}')
    if inst_name: bits.append(f'Institution: {inst_name}')
    summary=clean_text('. '.join(bits)+('.' if bits else ''))
    return {
      'name':name,
      'title':'Research author',
      'company':inst_name,
      'location':inst_loc,
      'profile_url':profile,
      'summary':summary,
      'skills':skills,
      'source_type':'openalex',
      'source_url':profile,
      'source_title':f'{name} on OpenAlex',
      'snippet':summary,
      'query':query
    }

def openalex_search(query, source_text='', state=None, max_works=OPENALEX_MAX_WORKS, max_authors=OPENALEX_MAX_AUTHORS):
    # Research/academic adapter: self-skips with 0 hits for ordinary non-research roles.
    state=state if isinstance(state,dict) else {}
    if state.get('backoff'): return []
    text=source_text or query
    if not is_openalex_research_role(text): return []
    topic=build_openalex_topic_query(text)
    if not topic: return []
    max_works=bounded(int(max_works or OPENALEX_MAX_WORKS), 5, OPENALEX_MAX_WORKS)
    max_authors=bounded(int(max_authors or OPENALEX_MAX_AUTHORS), 1, OPENALEX_MAX_AUTHORS)
    collected=state.setdefault('authors', {})
    returned=state.setdefault('returned_ids', set())

    data=openalex_request('works', {
      'search':topic,
      'per_page':max_works,
      'sort':'cited_by_count:desc',
      'select':'id,display_name,publication_year,cited_by_count,authorships,primary_topic,topics'
    })
    if data.get('_backoff'):
        state['backoff']=True
        return []
    works=list(data.get('results') or [])[:max_works]
    for work in works:
        for authorship in _openalex_pick_authors(work):
            author=(authorship or {}).get('author') or {}
            aid=_openalex_author_id(author) or clean_text(author.get('display_name') or '').lower()
            if not aid: continue
            insts=list(authorship.get('institutions') or [])
            inst_name,inst_loc=_openalex_institution(insts[0] if insts else {})
            if not inst_loc:
                countries=authorship.get('countries') or []
                if countries and isinstance(countries[0],str):
                    inst_loc=clean_text(countries[0])
            row=collected.get(aid)
            if not row:
                if len(collected)>=max_authors: continue
                collected[aid]={'author':author,'works':[],'institution_name':inst_name,'institution_location':inst_loc,'hydrated':{}}
                row=collected[aid]
            if work not in row['works']:
                row['works'].append(work)
            if inst_name and not row.get('institution_name'):
                row['institution_name']=inst_name
            if inst_loc and not row.get('institution_location'):
                row['institution_location']=inst_loc

    missing=[aid for aid,row in collected.items() if aid.startswith('A') and not row.get('institution_name')]
    hydrate_ids=[aid for aid in collected if aid.startswith('A')][:max_authors]
    # Hydrate only when a current institution or richer author evidence would help.
    if hydrate_ids and (missing or any(len(row.get('works') or [])==1 for row in collected.values())):
        try:
            hdata=openalex_request('authors', {
              'filter':'openalex_id:'+'|'.join(hydrate_ids),
              'per_page':len(hydrate_ids),
              'select':'id,display_name,last_known_institutions,cited_by_count,works_count,topics'
            })
            if hdata.get('_backoff'):
                state['backoff']=True
            else:
                by_id={}
                for item in hdata.get('results') or []:
                    hid=_openalex_author_id(item) or clean_text(item.get('id') or '')
                    if hid: by_id[hid]=item
                for aid,row in collected.items():
                    extra=by_id.get(aid)
                    if not extra: continue
                    row['hydrated']=extra
                    if extra.get('display_name'):
                        row['author']={**row['author'],'display_name':extra.get('display_name'),'id':extra.get('id') or row['author'].get('id')}
                    last=list(extra.get('last_known_institutions') or [])
                    if last:
                        name,loc=_openalex_institution(last[0])
                        if name: row['institution_name']=name
                        if loc: row['institution_location']=loc
        except Exception:
            pass

    hits=[]
    for aid,row in collected.items():
        if aid in returned: continue
        hit=_openalex_author_hit(row, query)
        if hit:
            returned.add(aid)
            hits.append(hit)
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
        geo=candidate_geo_eval(run, merged_c['location'])
        con.execute('''update candidates set title=?,company=?,location=?,profile_url=?,summary=?,skills_json=?,evidence_json=?,verify_json=?,
          base_score=?,learned_adjustment=?,score=?,evidence_coverage=?,search_round=min(search_round,?),geo_status=?,geo_evidence=?,geo_reason=?,updated_at=? where id=?''',
          (merged_c['title'],merged_c['company'],merged_c['location'],merged_c['profile_url'],merged,jdump(merged_skills),jdump(evidence),jdump(verify),base,adj,final,cov,search_round,geo['status'],geo['evidence'],geo['reason'],now(),existing['id']))
        add_source(con,existing['id'],hit,search_round)
        return existing['id'],False,geo
    base,adj,final,cov,evidence,verify,_=score_candidate(con,run['recruiter_key'],criteria,c)
    geo=candidate_geo_eval(run, c['location'])
    cid='cand_'+secrets.token_hex(6)
    rank=con.execute('select coalesce(max(rank_order),0)+1 n from candidates where run_id=?',(run['id'],)).fetchone()['n']
    con.execute('''insert into candidates(id,run_id,name,title,company,location,profile_url,summary,skills_json,evidence_json,verify_json,
      base_score,learned_adjustment,score,evidence_coverage,search_round,operator_status,rank_order,geo_status,geo_evidence,geo_reason,created_at,updated_at)
      values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (cid,run['id'],c['name'],c['title'],c['company'],c['location'],c['profile_url'],c['summary'],jdump(c['skills']),jdump(evidence),jdump(verify),base,adj,final,cov,search_round,'PENDING',rank,geo['status'],geo['evidence'],geo['reason'],now(),now()))
    add_source(con,cid,hit,search_round)
    return cid,True,geo

def execute_discovery(run_id, adapters, include_locator=True, per_query_limit=8, max_new_candidates=40):
    con=db(); run=con.execute('select * from runs where id=?',(run_id,)).fetchone()
    if not run: con.close(); raise KeyError('run not found')
    criteria=jload(run['criteria_json'],{}) or {}; plan=jload(run['search_plan_json'],{}) or {}
    rounds=plan.get('rounds') if isinstance(plan,dict) else plan
    rounds=rounds or []
    created=0; merged=0; total_hits=0; errors=[]; not_met_kept=0
    health=source_health(con,run['recruiter_key'])
    adapter_order=[a for a in adapters if a in {'internal_pool','public_web','github','stackexchange','openalex'}]
    se_state={}; oa_state={}
    se_text=clean_text(' '.join([run['role'] or '', run['brief'] or '', run['context'] or '']))
    for rd in rounds:
        if created>=max_new_candidates: break
        queries=rd.get('queries',[])
        if include_locator and rd.get('round')==2 and 'public_web' in adapter_order:
            queries=queries+(plan.get('profile_locator_queries') or [])
        for query in list(dict.fromkeys(queries)):
            if created>=max_new_candidates: break
            # Reuse previously-cached public discoveries (public_web / github / stackexchange /
            # openalex only) before spending a live provider query. internal_pool is never
            # read from or written to this cache.
            if created<max_new_candidates and ({'public_web','github','stackexchange','openalex'} & set(adapter_order)):
                cache_start=time.time(); cache_err=''; cache_status='OK'
                try:
                    cache_hits=public_graph_search(con,query,per_query_limit)
                except Exception as e:
                    cache_status='ERROR'; cache_err=str(e)[:800]; cache_hits=[]
                    errors.append({'adapter':'public_cache','query':query,'error':cache_err})
                cache_duration=int((time.time()-cache_start)*1000)
                con.execute('insert into discovery_queries(run_id,search_round,adapter,query,status,hits,error,duration_ms,created_at) values(?,?,?,?,?,?,?,?,?)',
                  (run_id,int(rd.get('round') or 1),'public_cache',query,cache_status,len(cache_hits),cache_err,cache_duration,now()))
                for hit in cache_hits:
                    preview=candidate_geo_eval(run, hit.get('location',''))
                    if preview['status']=='NOT_MET' and not_met_kept>=12:
                        continue
                    total_hits+=1
                    _,is_new,geo=stage_hit(con,run,criteria,hit,int(rd.get('round') or 1))
                    if is_new and geo['status']=='NOT_MET':
                        not_met_kept+=1
                    elif is_new: created+=1
                    else: merged+=1
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
                    elif adapter=='stackexchange':
                        if se_state.get('done') or se_state.get('backoff'):
                            continue
                        se_state['done']=True
                        hits=stackexchange_search(query,clean_text(se_text+' '+query),se_state,bounded(per_query_limit,STACKEXCHANGE_PER_TAG_MIN,STACKEXCHANGE_PER_TAG_MAX),STACKEXCHANGE_MAX_USERS)
                    elif adapter=='openalex':
                        if oa_state.get('done') or oa_state.get('backoff'):
                            continue
                        oa_state['done']=True
                        hits=openalex_search(query,clean_text(se_text+' '+query),oa_state,OPENALEX_MAX_WORKS,OPENALEX_MAX_AUTHORS)
                except Exception as e:
                    status='ERROR'; err=str(e)[:800]; errors.append({'adapter':adapter,'query':query,'error':err})
                duration=int((time.time()-start)*1000)
                con.execute('insert into discovery_queries(run_id,search_round,adapter,query,status,hits,error,duration_ms,created_at) values(?,?,?,?,?,?,?,?,?)',
                  (run_id,int(rd.get('round') or 1),adapter,query,status,len(hits),err,duration,now()))
                for hit in hits:
                    preview=candidate_geo_eval(run, hit.get('location',''))
                    if preview['status']=='NOT_MET' and not_met_kept>=12:
                        continue
                    total_hits+=1
                    _,is_new,geo=stage_hit(con,run,criteria,hit,int(rd.get('round') or 1))
                    if is_new and geo['status']=='NOT_MET':
                        not_met_kept+=1
                    elif is_new: created+=1
                    else: merged+=1
                    if adapter in ('public_web','github','stackexchange','openalex'):
                        try:
                            upsert_public_person(con,hit,adapter,hit.get('source_url',''),hit.get('provider','') or adapter,query,int(rd.get('round') or 1))
                        except Exception:
                            pass
                    if created>=max_new_candidates: break
    apply_geo_ranking(con, run_id)
    con.execute("update runs set status='OPERATOR_REVIEW',updated_at=? where id=?",(now(),run_id))
    log_event(con,run_id,'engine','DISCOVERY_COMPLETED',{'adapters':adapter_order,'created':created,'merged':merged,'hits':total_hits,'errors':errors[:10],'not_met':not_met_kept})
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
            geo_status=(c['geo_status'] if 'geo_status' in c.keys() else None) or 'UNKNOWN'
            item.update({'summary':c['summary'],'skills':jload(c['skills_json'],[]) or [],'base_score':c['base_score'],'learned_adjustment':c['learned_adjustment'],
              'score':c['score'],'evidence_coverage':c['evidence_coverage'],'search_round':c['search_round'],'operator_status':c['operator_status'],
              'operator_note':c['operator_note'],'rank_order':c['rank_order'],'published':bool(c['published']),'sources':sources,
              'geo_status':geo_status,'geo_evidence':(c['geo_evidence'] if 'geo_evidence' in c.keys() else '') or '',
              'geo_reason':(c['geo_reason'] if 'geo_reason' in c.keys() else '') or '',
              'geo_override':bool(c['geo_override']) if 'geo_override' in c.keys() and c['geo_override'] else False})
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
            cid,new,_=stage_hit(con,r,jload(r['criteria_json'],{}),hit,int(data.get('search_round') or 1)); apply_geo_ranking(con,rid); log_event(con,rid,'operator','CANDIDATE_ADDED',{'candidate_id':cid,'new':new}); con.commit()
            c=con.execute('select score,evidence_coverage from candidates where id=?',(cid,)).fetchone(); con.close(); return self.send_json({'id':cid,'score':c['score'],'evidence_coverage':c['evidence_coverage'],'new':new},201)
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/candidates/([^/]+)',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rid,cid=m.groups(); action=data.get('action'); con=db(); r=con.execute('select * from runs where id=?',(rid,)).fetchone(); c=con.execute('select * from candidates where id=? and run_id=?',(cid,rid)).fetchone()
            if not r or not c: con.close(); return self.send_json({'error':'not found'},404)
            if action=='approve':
                result=apply_operator_approve(con,c,bool(data.get('geo_override')))
                if not result.get('ok'):
                    con.close(); return self.send_json({'error':'geography override confirmation required','geo_status':result.get('geo_status'),'geo_reason':result.get('geo_reason')},409)
            elif action=='reject': con.execute("update candidates set operator_status='REJECTED',published=0,geo_override=0,updated_at=? where id=?",(now(),cid))
            elif action=='note': con.execute('update candidates set operator_note=?,updated_at=? where id=?',(clean_text(data.get('note')),now(),cid))
            elif action=='rank': con.execute('update candidates set rank_order=?,updated_at=? where id=?',(int(data.get('rank_order') or 999),now(),cid))
            elif action=='edit':
                merged={
                  'name':clean_text(data.get('name')) or c['name'],'title':clean_text(data.get('title')),'company':clean_text(data.get('company')),
                  'location':clean_text(data.get('location')),'profile_url':clean_text(data.get('profile_url')),'summary':clean_text(data.get('summary')),
                  'skills':data.get('skills') or []
                }
                base,adj,final,cov,evidence,verify,_=score_candidate(con,r['recruiter_key'],jload(r['criteria_json'],{}),merged)
                geo=candidate_geo_eval(r, merged['location'])
                override=0 if geo['status']!='NOT_MET' else int(c['geo_override'] if 'geo_override' in c.keys() and c['geo_override'] else 0)
                con.execute('''update candidates set name=?,title=?,company=?,location=?,profile_url=?,summary=?,skills_json=?,evidence_json=?,verify_json=?,
                  base_score=?,learned_adjustment=?,score=?,evidence_coverage=?,geo_status=?,geo_evidence=?,geo_reason=?,geo_override=?,updated_at=? where id=?''',
                  (merged['name'],merged['title'],merged['company'],merged['location'],merged['profile_url'],merged['summary'],jdump(merged['skills']),jdump(evidence),jdump(verify),base,adj,final,cov,geo['status'],geo['evidence'],geo['reason'],override,now(),cid))
                manual_hit={'source_type':'manual','source_url':merged['profile_url'],'source_title':'Operator-edited evidence','snippet':merged['summary'],'query':'operator edit'}
                add_source(con,cid,manual_hit,c['search_round'])
                apply_geo_ranking(con,rid)
            else: con.close(); return self.send_json({'error':'bad action'},400)
            log_event(con,rid,'operator','CANDIDATE_'+action.upper(),{'candidate_id':cid}); con.commit(); con.close(); return self.send_json({'ok':True})
        m=re.fullmatch(r'/api/admin/runs/([^/]+)/publish',path)
        if m:
            if not self.admin_ok(qs): return self.send_json({'error':'unauthorized'},401)
            rid=m.group(1); con=db()
            # NOT_MET geography is excluded unless the operator used approve as an override.
            approved=con.execute("""select count(*) n from candidates where run_id=? and operator_status='APPROVED'
              and (coalesce(geo_status,'UNKNOWN')<>'NOT_MET' or coalesce(geo_override,0)=1)""",(rid,)).fetchone()['n']
            if approved<1: con.close(); return self.send_json({'error':'approve at least one geography-eligible candidate'},400)
            con.execute("""update candidates set published=case
              when operator_status='APPROVED' and (coalesce(geo_status,'UNKNOWN')<>'NOT_MET' or coalesce(geo_override,0)=1) then 1
              else 0 end where run_id=?""",(rid,))
            con.execute("update runs set status='PUBLISHED',published_at=?,updated_at=? where id=?",(now(),now(),rid)); log_event(con,rid,'operator','SHORTLIST_PUBLISHED',{'count':approved}); con.commit(); con.close(); return self.send_json({'ok':True,'published':approved})
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
    print('Source adapters:', public_search_provider() or 'public web unconfigured', '| internal pool | GitHub | Stack Exchange | OpenAlex | manual')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
