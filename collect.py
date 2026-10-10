"""Official exhibition collector, standard library only. Keeps old entries on failure."""
import re,json,html,hashlib,datetime,urllib.request,urllib.parse,pathlib,sys
BASE=pathlib.Path(__file__).resolve().parent
DATA=BASE/'data.js' if (BASE/'data.js').exists() else BASE/'dist/data.js'
def text(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',s))).strip()
def field(s,tag,cls):
 m=re.search(r'<'+tag+r'\b[^>]*class=["\'][^"\']*\b'+re.escape(cls)+r'\b[^"\']*["\'][^>]*>(.*?)</'+tag+'>',s,re.S)
 return m.group(1) if m else ''
def dates(s,year=None):
 s=text(s)
 iso=re.findall(r'\b(20\d\d)-(\d{2})-(\d{2})\b',s)
 if len(iso)==2: parts=iso
 else:
  matches=re.findall(r'(?:(20\d\d)\s*年)?\s*(\d{1,2})月\s*(\d{1,2})日',s)
  if len(matches)!=2:return None
  parts=[]
  for y,m,d in matches:
   if y:year=int(y)
   if not year:return None
   parts.append((year,m,d))
 try:
  a,b=[datetime.date(*map(int,v)).isoformat() for v in parts]
  if a>b or (datetime.date.fromisoformat(b)-datetime.date.fromisoformat(a)).days>730:return None
  return a,b
 except ValueError:return None
def parse(key,s):
 s=re.sub(r'<!--.*?-->','',s,flags=re.S)
 result=[]
 if key=='hyogo':
  year=re.search(r'(20\d\d)年\s*年間スケジュール',s)
  if not year:raise ValueError('年間表の年を確認できません')
  for block in re.split(r'<div class="exhibition-item(?:\s|")',s)[1:]:
   title=field(block,'h3','exhibition-title').split('<span')[0]
   heading=block.split('exhibition-heading',1)[-1].split('exhibition-body',1)[0]
   period=dates(heading,int(year[1]))
   links=re.findall(r'<a[^>]+href="([^"]+)"[^>]*>詳細を見る',block)
   if title and period:result.append((text(title),*period,links[0] if links else SOURCES[key][2]))
 elif key=='osaka':
  for block in re.findall(r'<li\b[^>]*>(.*?)</li>',s,re.S):
   title=field(block,'p','single-title');period=dates(field(block,'p','single-date'))
   link=re.search(r'href="([^"]+)"',title)
   if title and period and link and '/exhibition-post/' in link[1]:result.append((text(title),*period,link[1]))
 elif key=='kyohaku':
  for block in re.split(r'<div class="exhibitionList__item"',s)[1:]:
   title=field(block,'h3','exhibitionList__title');period=dates(field(block,'div','exhibitionList__date'));link=re.search(r'<a[^>]+href="([^"]+)"',block)
   if title and period and link:result.append((text(title),*period,link[1]))
 elif key=='kobe':
  title=field(s,'span','detail_title');period=dates(field(s,'span','detail_date'))
  if title and period:result.append((text(title),*period,''))
 return list(dict.fromkeys(result))
SOURCES={'hyogo':('兵庫県立美術館','兵庫','https://www.artm.pref.hyogo.jp/exhibition/'),'osaka':('大阪中之島美術館','大阪','https://nakka-art.jp/'),'kyohaku':('京都国立博物館','京都','https://www.kyohaku.go.jp/jp/exhibitions/')}

SOURCES['kobe']=('神戸市立博物館','兵庫','https://www.kobecitymuseum.jp/exhibition/special')

def fetch_html(url):
 req=urllib.request.Request(url,headers={'User-Agent':'TenranTecho/1.0 personal exhibition calendar'})
 with urllib.request.urlopen(req,timeout=25) as r:return r.read(4000000).decode('utf-8')

def collect_kobe(raw):
 upcoming=fetch_html('https://www.kobecitymuseum.jp/exhibition/upcoming')
 links=list(dict.fromkeys(re.findall(r'href=[\"\'](https://www.kobecitymuseum.jp/exhibition/detail\?exhibition=\d+)[\"\']',raw+upcoming)))
 result=[]
 for link in links[:20]:
  rows=parse('kobe',fetch_html(link))
  result.extend((title,a,b,link) for title,a,b,_ in rows)
 return result

def fee_amount(value):
 value=text(value)
 if value=='無料':return 0
 m=re.fullmatch(r'([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+)円',value)
 return int(m[1].replace(',','')) if m else None

def parse_fee(key,raw):
 """Only read designated admission blocks; never search a whole page for prices."""
 raw=re.sub(r'<!--.*?-->','',raw,flags=re.S)
 if key=='hyogo':
  for table in re.findall(r'<table\b[^>]*class=["\'][^"\']*\bfee\b[^"\']*["\'][^>]*>.*?</table>',raw,re.S):
   rows=re.findall(r'<tr\b[^>]*>(.*?)</tr>',table,re.S)
   if not rows:continue
   headers=[text(c) for c in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>',rows[0],re.S)]
   if headers.count('当日')!=1:continue
   col=headers.index('当日')
   for row in rows[1:]:
    cells=[text(c) for c in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>',row,re.S)]
    if cells and cells[0]=='一般' and len(cells)>col:return fee_amount(cells[col])
 elif key=='osaka':
  for label,body in re.findall(r'<tr\b[^>]*>\s*<th\b[^>]*>(.*?)</th>\s*<td\b[^>]*>(.*?)</td>\s*</tr>',raw,re.S):
   if text(label)!='観覧料':continue
   if text(body)=='無料':return 0
   first=text(re.split(r'<br\s*/?>',body)[0])
   # Normal general price precedes explicitly labelled advance/group price.
   m=re.fullmatch(r'一般\s*([0-9,]+)円(?:[（(](?:前売|団体)[^）)]*[）)])?',first)
   if m:return fee_amount(m[1]+'円')
 elif key=='kobe':
  section=re.search(r'<h2>観覧料</h2>(.*?)(?:<h[23]|$)',raw,re.S)
  if section:
   m=re.search(r'<dt>当日券</dt>\s*<dd>(.*?)</dd>',section[1],re.S)
   if m:
    line=text(re.split(r'<br\s*/?>',m[1])[0]).replace(' ','')
    price=re.fullmatch(r'一般([0-9,]+)円',line)
    if price:return fee_amount(price[1]+'円')
 elif key=='kyohaku':
  m=re.search(r'<dl\b[^>]*id=["\']anchor_admission["\'][^>]*>(.*?)</dl>',raw,re.S)
  if not m:return None
  block=m[1]
  for label,value in re.findall(r'<tr\b[^>]*>\s*<th\b[^>]*>(.*?)</th>\s*<td\b[^>]*>(.*?)</td>\s*</tr>',block,re.S):
   if text(label)!='一般':continue
   value=text(value)
   direct=fee_amount(value)
   if direct is not None:return direct
   price=re.fullmatch(r'([0-9,]+)円（[0-9,]+円）',value)
   if price and '内は前売料金' in text(block):return fee_amount(price[1]+'円')
 return None

def update_fees(entries,today):
 cache={};counts={'取得成功':0,'確認できず':0,'取得失敗':0}
 for e in entries:
  key=e.get('sourceKey');url=e['url']
  if key not in SOURCES or e['end']<today:continue
  # Only individual exhibition pages. Gallery schedules have shared/conditional admission.
  path=urllib.parse.urlparse(url).path
  eligible=(key=='kobe' and path=='/exhibition/detail') or (key=='hyogo' and re.fullmatch(r'/exhibition/[tj]_\d+/index.html',path)) or (key=='osaka' and path.startswith('/exhibition-post/')) or (key=='kyohaku' and path.startswith('/jp/exhibitions/special/'))
  if not eligible:continue
  if url not in cache:
   try:
    req=urllib.request.Request(url,headers={'User-Agent':'TenranTecho/1.0 personal exhibition calendar'})
    with urllib.request.urlopen(req,timeout=20) as r:
     if urllib.parse.urlparse(r.url).hostname!=urllib.parse.urlparse(url).hostname:raise ValueError('Unexpected redirect')
     raw=r.read(4000000).decode('utf-8')
    amount=parse_fee(key,raw)
    cache[url]={'status':'取得成功' if amount is not None else '確認できず','checkedAt':today,'sourceUrl':url}
    if amount is not None:cache[url]['yen']=amount
   except Exception:cache[url]={'status':'取得失敗','checkedAt':today,'sourceUrl':url}
  e['admission']=dict(cache[url]);counts[e['admission']['status']]+=1
 return counts

def main():
 existing=json.loads(DATA.read_text().split('window.EXHIBITIONS=',1)[1].split(';\nwindow.COLLECTION_STATUS=',1)[0].strip().rstrip(';'))
 report={'checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':[]};today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date().isoformat();success=0
 for key,(museum,region,url) in SOURCES.items():
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'TenranTecho/1.0 personal exhibition calendar'})
   with urllib.request.urlopen(req,timeout=30) as r:raw=r.read(4000000).decode('utf-8')
   found=collect_kobe(raw) if key=='kobe' else parse(key,raw)
   if not found:raise ValueError('会期を確認できる展覧会がありません。既存情報を維持')
   for title,start,end,link in found:
    if end<today:continue
    parsed=urllib.parse.urlparse(link)
    if parsed.scheme!='https' or parsed.hostname!=urllib.parse.urlparse(url).hostname:continue
    # Preserve original IDs so favorites, photos and journal records keep working.
    norm=lambda v:re.sub(r'\s+','',v).translate(str.maketrans('ＮＨＫ５０','NHK50'))
    old=next((e for e in existing if e['museum']==museum and norm(e['title'])==norm(title)),None)
    legacy={'hyogo':[('蒐集のパッション','passion2026'),('前衛って何だ','zen2026')],'osaka':[('日曜美術館','nichibi2026')],'kyohaku':[('源氏物語','genji2026')]}
    if not old:
     for word,ident in legacy.get(key,[]):
      if word in title:old=next((e for e in existing if e['id']==ident),None);break
    if old:old.update(title=title,start=start,end=end,url=link,checkedAt=today,sourceKey=key)
    else:existing.append(dict(id=key+'-'+hashlib.sha256((title+start).encode()).hexdigest()[:14],title=title,short=title,museum=museum,region=region,start=start,end=end,url=link,bg={'兵庫':'#c6cdbb','大阪':'#c4d3d7','京都':'#d9cbb5'}[region],fg='#303b32',checkedAt=today,sourceKey=key))
   report['sources'].append(dict(museum=museum,status='取得成功',count=len(found)));success+=1
  except Exception as e:report['sources'].append(dict(museum=museum,status='取得失敗・既存情報を維持',error=str(e)))
 report['sources'].append(dict(museum='京都市京セラ美術館・国立西洋美術館',status='手動確認分を掲載・自動更新対象外'))
 report['admission']=update_fees(existing,today)
 DATA.write_text('window.EXHIBITIONS='+json.dumps(existing,ensure_ascii=False,indent=2)+';\nwindow.COLLECTION_STATUS='+json.dumps(report,ensure_ascii=False)+';\n')
 print(json.dumps(report,ensure_ascii=False,indent=2))
 if not success:sys.exit(1)
if __name__=='__main__':main()
