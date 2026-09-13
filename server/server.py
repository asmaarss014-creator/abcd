#!/usr/bin/env python3
import base64, hashlib, hmac, json, mimetypes, os, secrets, sqlite3, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get('DARA_DB', ROOT / 'data' / 'dara_parts.db'))
WEB = ROOT / 'web'
ASSETS = ROOT / 'assets'
PORT = int(os.environ.get('DARA_PORT', '8765'))
HOST = os.environ.get('DARA_HOST', '0.0.0.0')
SESSION_HOURS = 12

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')), enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS manufacturers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, image_path TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS models(id INTEGER PRIMARY KEY AUTOINCREMENT, manufacturer_id INTEGER NOT NULL, name TEXT NOT NULL, year INTEGER DEFAULT 0, UNIQUE(manufacturer_id,name), FOREIGN KEY(manufacturer_id) REFERENCES manufacturers(id));
CREATE TABLE IF NOT EXISTS parts(id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL, model_id INTEGER, name TEXT NOT NULL, part_number TEXT DEFAULT '', specification TEXT DEFAULT '', compatibility TEXT DEFAULT '', notes TEXT DEFAULT '', FOREIGN KEY(category_id) REFERENCES categories(id), FOREIGN KEY(model_id) REFERENCES models(id));
CREATE TABLE IF NOT EXISTS inventory(part_id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL DEFAULT 0, condition TEXT DEFAULT '', tested INTEGER NOT NULL DEFAULT 0, buy_min REAL DEFAULT 0, buy_mid REAL DEFAULT 0, buy_max REAL DEFAULT 0, sell_min REAL DEFAULT 0, sell_mid REAL DEFAULT 0, sell_max REAL DEFAULT 0, FOREIGN KEY(part_id) REFERENCES parts(id) ON DELETE CASCADE);
CREATE INDEX IF NOT EXISTS ix_parts_search ON parts(name,part_number,specification);
'''

DEFAULT_PARTS = [
('Motherboard','700','1200'),('CPU','300','500'),('RAM','300','500'),('HDD','400','500'),('LED Panel','300','900'),('LCD Cable Ribbon','120','200'),('Keyboard','200','300'),('Battery Pack','300','700'),('DC Charging Jack','50','100'),('Cooling Fan','100','300'),('Heat Sink Pipes','50','200'),('Speaker Kit','200','800'),('Wifi Card','100','300'),('Bluetooth Card','50','150'),('Webcam / Camera Module','200','400'),('CD/DVD Drive Unit','150','200'),('USB Port Board','50','150'),('Power Button Board','300','400'),('Upper Casing / Top Case','500','2000'),('Bottom Case Shield','500','2000'),('LCD Cover','500','1200'),('LCD Bezel Border','200','500'),('HDD Cable / Port','50','300'),('Keyboard Interconnect Flex','100','300'),('Chassis Screw Kit','200','1200'),('Touchpad Plate','200','300'),('Touchpad Flex Cable','100','300'),('SSD','300','500'),('Low-End Dedicated GPU','100','100'),('Mid-End Dedicated GPU','200','500'),('CMOS Battery','20','50'),('Daughter Board / Audio Board','150','400'),('LCD Screen Hinges','150','400'),('Universal Charger & Cord','400','800')
]

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def pwd_hash(password, salt=None):
    salt=salt or secrets.token_bytes(16); rounds=180000
    d=hashlib.pbkdf2_hmac('sha256', password.encode(), salt, rounds)
    return f'pbkdf2${rounds}${base64.b64encode(salt).decode()}${base64.b64encode(d).decode()}'

def pwd_ok(password, stored):
    try:
        _, rounds, salt, digest=stored.split('$',3)
        d=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.b64decode(salt),int(rounds))
        return hmac.compare_digest(base64.b64encode(d).decode(),digest)
    except Exception: return False

def init_db():
    c=connect(); c.executescript(SCHEMA)
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0:
        c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',('admin',pwd_hash('DaraAdmin123!'),'admin',int(time.time())))
        c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',('user',pwd_hash('DaraUser123!'),'user',int(time.time())))
    if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0]==0:
        for n,mn,mx in DEFAULT_PARTS:
            c.execute('INSERT INTO categories(name,image_path) VALUES(?,?)',(n,'/assets/dara-parts-background.png'))
            cid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO parts(category_id,name,notes) VALUES(?,?,?)',(cid,n,'Default Dara Parts category'))
            pid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            mid=(float(mn)+float(mx))/2
            c.execute('INSERT INTO inventory(part_id,quantity,condition,tested,buy_min,buy_mid,buy_max,sell_min,sell_mid,sell_max) VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,0,'',0,float(mn),mid,float(mx),float(mn),mid,float(mx)))
    c.commit(); c.close()

def auth(handler):
    h=handler.headers.get('Authorization',''); token=h[7:] if h.startswith('Bearer ') else ''
    if not token: return None
    c=connect(); row=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>? AND u.enabled=1',(token,int(time.time()))).fetchone(); c.close(); return row

def j(handler, code, obj):
    b=json.dumps(obj,ensure_ascii=False).encode(); handler.send_response(code); handler.send_header('Content-Type','application/json; charset=utf-8'); handler.send_header('Content-Length',str(len(b))); handler.end_headers(); handler.wfile.write(b)

class H(BaseHTTPRequestHandler):
    server_version='DaraParts/Universal-1.0'
    def log_message(self,fmt,*args): print(fmt%args)
    def body(self):
        n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=='/api/health': return j(self,200,{'ok':True,'service':'Dara Parts','server':sys.platform,'db':str(DB_PATH)})
        if p.path in ('/','/index.html'):
            data=(WEB/'index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        if p.path.startswith('/assets/'):
            f=ROOT/p.path.lstrip('/');
            if f.exists() and f.is_file():
                data=f.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(str(f))[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        u=auth(self)
        if not u: return j(self,401,{'ok':False,'error':'Login required'})
        c=connect(); q=parse_qs(p.query)
        if p.path=='/api/me': c.close(); return j(self,200,{'ok':True,'user':{'username':u['username'],'role':u['role']}})
        if p.path=='/api/manufacturers': rows=c.execute('SELECT * FROM manufacturers ORDER BY name').fetchall()
        elif p.path=='/api/categories': rows=c.execute('SELECT * FROM categories ORDER BY name').fetchall()
        elif p.path=='/api/models':
            brand=q.get('manufacturer',[''])[0]; sql='SELECT m.id,m.name,m.year,mf.name manufacturer FROM models m JOIN manufacturers mf ON mf.id=m.manufacturer_id'; args=[]
            if brand: sql+=' WHERE mf.name=?'; args=[brand]
            rows=c.execute(sql+' ORDER BY mf.name,m.name',args).fetchall()
        elif p.path=='/api/parts':
            search=q.get('search',[''])[0].strip().lower(); cat=q.get('category',[''])[0]; brand=q.get('manufacturer',[''])[0]; model=q.get('model',[''])[0]
            sql='''SELECT p.id,p.name,ca.name category,COALESCE(mf.name,'') manufacturer,COALESCE(m.name,'') model,COALESCE(m.year,0) year,p.part_number,p.specification,p.compatibility,p.notes,COALESCE(i.quantity,0) quantity,COALESCE(i.condition,'') condition,COALESCE(i.tested,0) tested,i.buy_min,i.buy_mid,i.buy_max,i.sell_min,i.sell_mid,i.sell_max FROM parts p JOIN categories ca ON ca.id=p.category_id LEFT JOIN models m ON m.id=p.model_id LEFT JOIN manufacturers mf ON mf.id=m.manufacturer_id LEFT JOIN inventory i ON i.part_id=p.id WHERE 1=1'''; args=[]
            if search: sql+=' AND lower(p.name||" "||p.part_number||" "||p.specification||" "||p.compatibility||" "||ca.name||" "||COALESCE(mf.name,"")||" "||COALESCE(m.name,"")) LIKE ?'; args.append('%'+search+'%')
            if cat: sql+=' AND ca.name=?'; args.append(cat)
            if brand: sql+=' AND mf.name=?'; args.append(brand)
            if model: sql+=' AND m.name=?'; args.append(model)
            rows=c.execute(sql+' ORDER BY ca.name,mf.name,m.name,p.name LIMIT 1000',args).fetchall()
        elif p.path=='/api/users' and u['role']=='admin': rows=c.execute('SELECT id,username,role,enabled,created_at FROM users ORDER BY username').fetchall()
        else: c.close(); return j(self,403 if p.path=='/api/users' else 404,{'ok':False,'error':'Not found or forbidden'})
        c.close(); return j(self,200,{'ok':True,'items':[dict(r) for r in rows]})
    def do_POST(self):
        p=urlparse(self.path); data=self.body()
        if p.path=='/api/login':
            c=connect(); u=c.execute('SELECT * FROM users WHERE username=?',(str(data.get('username','')).strip(),)).fetchone()
            if not u or not u['enabled'] or not pwd_ok(str(data.get('password','')),u['password_hash']): c.close(); return j(self,401,{'ok':False,'error':'Invalid username or password'})
            t=secrets.token_urlsafe(36); c.execute('INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)',(t,u['id'],int(time.time())+SESSION_HOURS*3600)); c.commit(); c.close(); return j(self,200,{'ok':True,'token':t,'user':{'username':u['username'],'role':u['role']}})
        u=auth(self)
        if not u: return j(self,401,{'ok':False,'error':'Login required'})
        c=connect()
        if p.path=='/api/logout':
            tok=self.headers.get('Authorization','')[7:]; c.execute('DELETE FROM sessions WHERE token=?',(tok,)); c.commit(); c.close(); return j(self,200,{'ok':True})
        if p.path=='/api/users' and u['role']=='admin':
            try: c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',(data['username'],pwd_hash(data['password']),data.get('role','user'),int(time.time()))); c.commit(); c.close(); return j(self,201,{'ok':True})
            except Exception as e: c.close(); return j(self,400,{'ok':False,'error':str(e)})
        if p.path=='/api/inventory' and u['role']=='admin':
            fields=['quantity','condition','tested','buy_min','buy_mid','buy_max','sell_min','sell_mid','sell_max']; vals=[data.get(x,0) for x in fields]
            c.execute('''INSERT INTO inventory(part_id,quantity,condition,tested,buy_min,buy_mid,buy_max,sell_min,sell_mid,sell_max) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(part_id) DO UPDATE SET quantity=excluded.quantity,condition=excluded.condition,tested=excluded.tested,buy_min=excluded.buy_min,buy_mid=excluded.buy_mid,buy_max=excluded.buy_max,sell_min=excluded.sell_min,sell_mid=excluded.sell_mid,sell_max=excluded.sell_max''',(data['part_id'],*vals)); c.commit(); c.close(); return j(self,200,{'ok':True})
        c.close(); return j(self,403,{'ok':False,'error':'Forbidden'})

if __name__=='__main__':
    init_db(); print(f'Dara Parts Server: http://{HOST}:{PORT}'); print('Admin: admin / DaraAdmin123!'); print('User : user / DaraUser123!'); ThreadingHTTPServer((HOST,PORT),H).serve_forever()
