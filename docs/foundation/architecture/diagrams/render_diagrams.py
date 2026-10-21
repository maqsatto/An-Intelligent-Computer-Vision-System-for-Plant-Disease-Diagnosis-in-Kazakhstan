from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from xml.sax.saxutils import escape
import math

OUT = Path(__file__).resolve().parent
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
BG = '#f6f9f7'
INK = '#153f34'
MUTED = '#516b62'
GREEN = '#286e56'
LINE = '#76948a'
PALE = '#e8f2ec'
WHITE = '#ffffff'

class Canvas:
    def __init__(self, width, height):
        self.w, self.h, self.scale = width, height, 2
        self.image = Image.new('RGB', (width*2, height*2), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', f'<rect width="100%" height="100%" fill="{BG}"/>']

    def rect(self, x,y,w,h, fill=WHITE, stroke=GREEN, sw=2, rx=16, dash=False):
        d = ' stroke-dasharray="10 7"' if dash else ''
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
        self.draw.rounded_rectangle((x*2,y*2,(x+w)*2,(y+h)*2),radius=rx*2,fill=fill,outline=None if dash else stroke,width=sw*2)
        if dash:
            self.line([(x+rx,y),(x+w-rx,y)],stroke,sw,True,False,svg=False)
            self.line([(x+w,y+rx),(x+w,y+h-rx)],stroke,sw,True,False,svg=False)
            self.line([(x+rx,y+h),(x+w-rx,y+h)],stroke,sw,True,False,svg=False)
            self.line([(x,y+rx),(x,y+h-rx)],stroke,sw,True,False,svg=False)

    def ellipse(self,x,y,w,h,fill=WHITE,stroke=GREEN,sw=2):
        self.svg.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        self.draw.ellipse((x*2,y*2,(x+w)*2,(y+h)*2),fill=fill,outline=stroke,width=sw*2)

    def line(self, pts, color=LINE, width=3, dash=False, arrow=True, svg=True):
        if svg:
            d = ' stroke-dasharray="10 7"' if dash else ''
            s=' '.join(f'{x},{y}' for x,y in pts)
            self.svg.append(f'<polyline points="{s}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"{d}/>')
        for p,q in zip(pts,pts[1:]):
            x,y=p;xx,yy=q
            if not dash:
                self.draw.line((x*2,y*2,xx*2,yy*2),fill=color,width=width*2)
            else:
                dist=math.hypot(xx-x,yy-y)
                if not dist: continue
                ux,uy=(xx-x)/dist,(yy-y)/dist
                t=0
                while t<dist:
                    end=min(t+10,dist)
                    self.draw.line(((x+ux*t)*2,(y+uy*t)*2,(x+ux*end)*2,(y+uy*end)*2),fill=color,width=width*2)
                    t+=17
        if arrow:
            x,y=pts[-1];x0,y0=pts[-2]
            angle=math.atan2(y-y0,x-x0)
            a=(x-15*math.cos(angle)+6*math.sin(angle),y-15*math.sin(angle)-6*math.cos(angle))
            b=(x-15*math.cos(angle)-6*math.sin(angle),y-15*math.sin(angle)+6*math.cos(angle))
            points=[(x,y),a,b]
            if arrow == 'open':
                open_points=[a,(x,y),b]
                if svg:
                    self.svg.append('<polyline points="'+' '.join(f'{px},{py}' for px,py in open_points)+f'" fill="none" stroke="{color}" stroke-width="{width}"/>')
                self.draw.line([(px*2,py*2) for px,py in open_points],fill=color,width=width*2)
            else:
                if svg:
                    self.svg.append('<polygon points="'+' '.join(f'{px},{py}' for px,py in points)+f'" fill="{color}"/>')
                self.draw.polygon([(px*2,py*2) for px,py in points],fill=color)

    def text(self,x,y,lines,size=24,color=INK,bold=False,anchor='middle',lineheight=None):
        if isinstance(lines,str): lines=lines.split('\n')
        lh=lineheight or size*1.38
        top=y-(len(lines)-1)*lh/2
        font=ImageFont.truetype(BOLD if bold else FONT,size*2)
        weight='bold' if bold else 'normal'
        for i,line in enumerate(lines):
            yy=top+i*lh
            self.svg.append(f'<text x="{x}" y="{yy}" fill="{color}" font-family="DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" dominant-baseline="middle">{escape(line)}</text>')
            anc={'middle':'mm','start':'lm','end':'rm'}[anchor]
            self.draw.text((x*2,yy*2),line,font=font,fill=color,anchor=anc)

    def label(self,x,y,lines,w,size=21):
        if isinstance(lines,str): lines=lines.split('\n')
        h=len(lines)*size*1.38+18
        self.rect(x-w/2,y-h/2,w,h,fill=BG,stroke=BG,sw=0,rx=8)
        self.text(x,y,lines,size=size,color=MUTED)

    def card(self,x,y,w,h,title,body=(),fill=WHITE,dash=False):
        self.rect(x,y,w,h,fill=fill,dash=dash)
        if isinstance(title,str):title=[title]
        titley=y+42 if body else y+h/2
        self.text(x+w/2,titley,title,size=27,bold=True)
        if body: self.text(x+w/2,y+h*0.68,body,size=22,color=MUTED)

    def actor(self,x,y,lines):
        self.ellipse(x-18,y-18,36,36,fill=BG,stroke=INK,sw=3)
        self.line([(x,y+18),(x,y+82)],INK,3,False,False)
        self.line([(x-38,y+40),(x+38,y+40)],INK,3,False,False)
        self.line([(x,y+82),(x-34,y+122)],INK,3,False,False)
        self.line([(x,y+82),(x+34,y+122)],INK,3,False,False)
        self.text(x,y+160,lines,size=23,bold=True)

    def usecase(self,x,y,w,h,lines,fill=WHITE):
        self.ellipse(x-w/2,y-h/2,w,h,fill=fill,stroke=GREEN,sw=2)
        self.text(x,y,lines,size=23)

    def title(self,title,subtitle):
        self.text(58,63,title,42,bold=True,anchor='start')
        self.text(60,118,subtitle,21,color=MUTED,anchor='start')

    def save(self,name):
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/f'{name}.svg').write_text('\n'.join(self.svg+['</svg>']))
        self.image.resize((self.w,self.h),Image.Resampling.LANCZOS).save(OUT/f'{name}.png')

def context():
    c=Canvas(1700,1140)
    c.title('AgroVision · Контекст системы','Проектная схема: наблюдения, предварительная оценка фото и исследовательские данные')
    # Same seven directed relations as context.mmd.
    c.line([(440,230),(620,230),(620,390)])
    c.line([(550,490),(490,490),(490,300),(440,300)])
    c.line([(1260,230),(1080,230),(1080,390)])
    c.line([(1150,490),(1210,490),(1210,300),(1260,300)])
    c.line([(1260,815),(1080,815),(1080,640)])
    c.line([(1150,570),(1210,570),(1210,880),(1260,880)])
    c.line([(440,815),(620,815),(620,640)])
    c.card(60,180,380,170,'Растениевод',['Фото и наблюдения','поддержанных культур'])
    c.card(1260,180,380,170,'Эксперт по растениям',['Референсная разметка','разрешенных образцов'])
    c.card(1260,760,380,170,['Технический оператор'],['ML-исследователь','и выпуск моделей'])
    c.card(60,760,380,170,'Источники данных',['Проверенные датасеты','и локальные образцы'])
    c.rect(550,390,600,250,fill=INK,stroke=INK)
    c.text(850,454,'AgroVision',42,bold=True,color=WHITE)
    c.text(850,541,['Наблюдения и предварительная','оценка фото растений'],29,color=WHITE)
    c.label(665,191,['Фото, культура,','наблюдение'],330)
    c.label(335,435,['Предварительная','оценка, история'],300)
    c.label(1045,190,['Референсные метки','и уровень подтверждения'],355)
    c.label(1395,435,['Разрешенная','исследовательская выборка'],360)
    c.label(1060,866,['Конфигурации','и model release'],320)
    c.label(1370,680,['Отчеты, версии','и ошибки'],300)
    c.label(645,866,['Данные с provenance','для offline исследования'],360)
    c.text(850,1020,['Внутренние API, worker, PostgreSQL и storage показаны на компонентной схеме.',
                     'Данные для исследования не означают готовую локальную валидацию. Роли эксперта и оператора — проектные.'],21,color=MUTED)
    c.save('context')

def components():
    c=Canvas(1800,1550)
    c.title('AgroVision · Компоненты','Один Python codebase, два процесса; mobile — текущий клиент, web — будущая фаза')
    c.rect(60,425,1680,440,fill=PALE,stroke='#bfd5c8',sw=2,rx=22)
    c.text(90,455,'BACKEND APPLICATION · ОБЩИЕ МОДУЛИ И МИГРАЦИИ',22,bold=True,color=GREEN,anchor='start')
    # Ten relations, corresponding to components.mmd.
    c.line([(645,252),(575,252)],dash=True)
    c.line([(1155,252),(1225,252)],dash=True)
    c.line([(320,315),(320,495)])
    c.line([(1480,315),(1480,370),(435,370),(435,495)],dash=True)
    c.line([(1290,595),(1290,700)])
    c.line([(350,725),(350,1040)])
    c.line([(950,550),(835,550),(835,930),(500,930),(500,1040)])
    c.line([(750,650),(875,650),(875,990),(1150,990),(1150,1040)])
    c.line([(1630,550),(1695,550),(1695,950),(1450,950),(1450,1040)])
    c.line([(750,1380),(1290,1380),(1290,1200)],dash=True)
    c.card(65,190,510,125,'React Native mobile',['UI, camera, persistent drafts'])
    c.card(645,190,510,125,'Shared TypeScript',['API client и generated types'])
    c.card(1225,190,510,125,'Будущий React web',['Только архитектурный план'],dash=True)
    c.card(120,495,630,230,'FastAPI API',['identity · catalog · farms','observations · assessments · feedback'])
    c.card(950,495,680,100,'Inference worker',['claim · lease · retry · result'])
    c.card(950,700,680,100,'ml/runtime',['preprocessing · ONNX · postprocessing'])
    c.card(120,1040,630,160,'PostgreSQL',['metadata · assessment_jobs · results','model-version metadata'])
    c.card(950,1040,680,160,'Private S3-compatible storage',['ready photos · immutable model bundles'])
    c.card(120,1320,630,130,'Offline training / evaluation',['данные · splits · train · evaluate · export'])
    c.label(225,397,'HTTPS /v1',200)
    c.label(1030,371,'Будущий HTTPS /v1',300)
    c.label(1290,648,'Локальный Python вызов',400)
    c.label(280,881,['Metadata; assessment + job','одной транзакцией'],410)
    c.label(655,930,['Claim, lease,','fenced result commit'],310)
    c.label(1118,989,['Private upload /','authorized URL'],280)
    c.label(1555,915,['Ready photo','и pinned bundle'],290)
    c.label(1045,1332,['Проверенный immutable','bundle + отчет'],400)
    c.text(900,1498,'Пунктир: build-time зависимости, будущий web или перенос модельного артефакта; смысл указан рядом.',21,color=MUTED)
    c.save('components')

def use_cases():
    c=Canvas(1960,1840)
    c.title('AgroVision · UML Use Case','Проектные актеры и цели; include/extend показывают смысловую связь, а не очередность HTTP-запросов')
    c.rect(280,190,1400,1510,fill=WHITE,stroke='#a9c4b6',sw=2,rx=8)
    c.text(980,222,'ГРАНИЦА СИСТЕМЫ AGROVISION',25,bold=True,color=GREEN)
    ymap={'UC01':300,'UC02':450,'UC03':600,'UC04':750,'UC05':900,'UC06':1050,'UC07':1200,'UC08':1350,'UC11':1500}
    # Fourteen plain actor associations, same as use_cases.puml.
    for key,y in ymap.items(): c.line([(168,870),(370,y)],'#92aaa0',2,False,False)
    c.line([(1772,850),(1600,850)],'#92aaa0',2,False,False)
    c.line([(1810,790),(1730,790),(1730,450),(930,450)],'#92aaa0',2,False,False)
    c.line([(1772,1390),(1600,1200)],'#92aaa0',2,False,False)
    c.line([(1772,1390),(1600,1500)],'#92aaa0',2,False,False)
    c.line([(1848,1390),(1900,1390),(1900,385),(930,385),(930,450)],'#92aaa0',2,False,False)
    # Two includes and one optional extension.
    c.line([(930,600),(1040,600)],GREEN,2,True,'open')
    c.line([(1320,1250),(1320,1305)],GREEN,2,True,'open')
    c.line([(930,1350),(985,1350),(985,750),(930,750)],GREEN,2,True,'open')
    left={
        'UC01':['UC-01','Просмотреть поддерживаемые','культуры'],
        'UC02':['UC-02','Войти / завершить сессию'],
        'UC03':['UC-03','Отправить фото на оценку'],
        'UC04':['UC-04','Получить результат','и следующее действие'],
        'UC05':['UC-05','Просмотреть историю'],
        'UC06':['UC-06','Связать наблюдение','с полем / сезоном'],
        'UC07':['UC-07','Сохранить offline-черновик'],
        'UC08':['UC-08','Оставить отзыв о результате'],
        'UC11':['UC-11','Удалить собственное','наблюдение']}
    for key,lines in left.items(): c.usecase(650,ymap[key],560,112,lines)
    c.usecase(1320,600,560,112,['Проверить доступ','и пригодность фото'],PALE)
    c.usecase(1320,850,560,112,['UC-09','Аннотировать','исследовательский образец'])
    c.usecase(1320,1200,560,100,['UC-10','Проверить и активировать модель'])
    c.usecase(1320,1360,560,110,['Проверить модельный bundle'],PALE)
    c.usecase(1320,1500,560,112,['UC-12','Выполнить оценку','и получить отчет'])
    c.actor(130,830,['Растениевод'])
    c.actor(1810,810,['Эксперт','по растениям'])
    c.actor(1810,1350,['Технический','оператор /','ML-исследователь'])
    c.label(985,565,'«include»',108,18)
    c.label(1440,1280,'«include»',150,18)
    c.label(985,1030,['«extend»','по желанию'],112,17)
    c.text(980,1753,['Сплошная линия — участие актера. Пунктирная стрелка — UML include или extend.',
                     'Offline-черновик может завершиться без сети. Наличие реальных экспертных участников еще требуется подтвердить.'],22,color=MUTED)
    c.save('use_cases')

if __name__=='__main__':
    context();components();use_cases()
    print('Rendered 3 SVG and 3 PNG diagrams from matching node/edge specifications.')
