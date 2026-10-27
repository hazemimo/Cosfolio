"""Offline template geometry. Prepared reference plates are ordinary local files."""
from .sources import SOURCE_FILES,EXTRA_TEMPLATES

TEMPLATES = {
    'party': {'name':'气球杂志 · 经典三格','size':(2000,2831),
        'slots':[(90,173,1039,1208),(1196,173,651,1208),(96,1451,1750,1274)],
        'labels':['左上 · 特写','右上 · 站姿','下方 · 横幅'],
        'note':'使用提供的去人底图，保留实拍气球与金框', 'plate':'party.png'},
    'halloween': {'name':'万圣夜 · 三格杂志','size':(2000,2831),
        'slots':[(90,173,1039,1208),(1196,173,651,1208),(96,1451,1750,1274)],
        'labels':['左上 · 特写','右上 · 站姿','下方 · 横幅'],
        'note':'原创万圣节配色，沿用三格版式'},
    'card': {'name':'万圣夜 · 真人卡面','size':(1800,2400),
        'slots':[(65,65,1670,2100)],'labels':['卡面 · 主体'],
        'note':'原创真人卡面试作，含前景星星和卡框'},
    'balloon_five': {'name':'气球杂志 · 五格拼贴','size':(1420,2048),
        'slots':[(47,131,626,870),(722,131,593,870),(47,1050,626,925),(722,1050,593,438),(722,1540,593,435)],
        'labels':['左上 · 竖幅','右上 · 竖幅','左下 · 主图','右中 · 特写','右下 · 特写'],
        'note':'参考 De7Dneo：两张竖幅、一张大图和两张特写', 'plate':'balloon_five.png', 'fit':'height', 'text_style':'top'},
    'balloon_quad': {'name':'气球杂志 · 大横幅四格','size':(1451,2048),
        'slots':[(116,129,1265,870),(116,1048,625,438),(116,1530,625,438),(791,1048,590,920)],
        'labels':['上方 · 主横幅','左中 · 特写','左下 · 特写','右下 · 竖幅'],
        'note':'参考 TLOf33y：一张大横幅配三张小图', 'plate':'balloon_quad.png','fit':'height','text_style':'top'},
    'balloon_full': {'name':'气球写真 · 满版金框','size':(1423,2048),
        'slots':[(92,136,1240,1818)],'labels':['中央 · 主体'],
        'note':'参考 KhsoJZw：大幅写真与实拍气球', 'plate':'balloon_full.png','fit':'height','text_style':'top'},
    'balloon_air': {'name':'气球写真 · 留白竖幅','size':(1436,2047),
        'slots':[(120,143,1225,1787)],'labels':['中央 · 主体'],
        'note':'参考 Rz7ouuF：大面积留白，底部气球', 'plate':'balloon_air.png','fit':'height','text_style':'top'},
    'dream_mosaic': {'name':'Dream · 五格拼版','size':(2000,2045),
        'slots':[(35,28,1010,802),(35,854,540,1156),(598,854,450,472),(598,1350,450,660),(1073,28,892,1982)],
        'labels':['左上 · 横幅','左下 · 竖幅','中上 · 特写','中下 · 特写','右侧 · 主图'],
        'note':'参考 Dream Sensation 3：接近方形的非对称五格', 'plate':'dream_mosaic.png','fit':'height','text_style':'band'},
    'dream_qa': {'name':'Dream · 蓝色访谈五格','size':(1000,1030),
        'slots':[(43,33,606,477),(666,33,326,477),(525,523,213,226),(752,523,240,226),(525,763,467,239)],
        'labels':['左上 · 横幅','右上 · 竖幅','中左 · 特写','中右 · 特写','右下 · 横幅'],
        'note':'参考 Dream Sensation 2：五个照片区域与访谈侧栏', 'plate':'dream_qa.png','fit':'height','text_style':'qa'},
    'blue_hero': {'name':'Endless · 主图与三连拍','size':(1432,2048),
        'slots':[(405,10,1005,1905),(51,12,339,595),(51,627,339,672),(51,1325,339,584)],
        'labels':['右侧 · 主图','左上 · 特写','左中 · 特写','左下 · 特写'],
        'note':'参考 Endless Parade 2：一张主图加三张侧栏照片', 'plate':'blue_hero.png','fit':'height','text_style':'bottom'},
    'blue_duo': {'name':'Endless · 双主图与侧栏','size':(1432,2048),
        'slots':[(20,12,845,1125),(20,1160,845,780),(925,1235,390,705)],
        'labels':['左上 · 主图','左下 · 横幅','右下 · 特写'],
        'note':'参考 Endless Parade 3：上下双主图与窄侧栏', 'plate':'blue_duo.png','fit':'height','text_style':'message'},
    'clean_portrait': {'name':'Endless · 极简留白写真','size':(1000,1430),
        'slots':[(230,65,725,1245)],'labels':['右侧 · 主体'],
        'note':'参考 Endless Parade 1：纯白留白、细线与花纹', 'plate':'clean_portrait.png','fit':'height','text_style':'minimal'},
    'white_sidebar': {'name':'LisAni · 蓝色侧栏写真','size':(1000,1433),
        'slots':[(300,75,655,1275)],'labels':['右侧 · 主体'],
        'note':'参考 LisAni 015：白底写真和蓝色姓名侧栏', 'plate':'white_sidebar.png','fit':'height','text_style':'sidebar'},
}

TEMPLATES.update(EXTRA_TEMPLATES)
# Use the supplied page's native geometry, rather than silently enlarging it.
TEMPLATES['party'].update(size=(1446,2048),
    slots=[(65,125,751,874),(865,125,471,874),(69,1050,1265,922)],text_style='top')
# Native-page audit: earlier approximate coordinates cut the middle black panel
# short and missed the lower white panel in Dream 3. Keep the plate untouched.
TEMPLATES['dream_mosaic'].update(
    slots=[(0,45,1051,816),(0,875,551,1138),(560,866,489,606),
           (561,1483,488,527),(1061,45,881,1966)],radii=[36,36,36,36,38])
TEMPLATES['dream_qa'].update(
    slots=[(34,25,613,486),(660,25,340,488),(519,518,224,234),
           (754,518,246,234),(520,761,480,246)],radii=[14,14,10,10,12])
TEMPLATES['blue_hero'].update(
    slots=[(410,8,1008,1908),(51,9,343,602),(2,622,397,689),(58,1323,342,594)])
TEMPLATES['blue_duo'].update(
    slots=[(18,0,844,1146),(19,1157,843,891),(928,1241,381,802)])
TEMPLATES['seiyuu_note']['slots']=[(65,52,275,565),(365,142,134,270)]
# Printed material that intentionally crosses a photo region is a separate
# foreground layer. Users can replace its mask without editing source plates.
TEMPLATES['clean_portrait']['foreground_regions']=[(0,1280,1000,150),(80,75,170,450),(100,1080,850,7)]
TEMPLATES['white_sidebar']['foreground_regions']=[(110,1000,300,315)]
TEMPLATES['balloon_signature']['foreground_regions']=[(860,1440,560,595)]
TEMPLATES['seiyuu_note']['foreground_regions']=[(65,0,240,112),(0,320,200,309),(350,0,149,90)]
TEMPLATES['seiyuu_profile']['foreground_regions']=[(415,42,500,100)]
for key,(source,reference) in SOURCE_FILES.items():
    TEMPLATES[key].update(plate=f'v04/plates/{key}.webp',source=source,
                          reference=f'v04/originals/{reference}')
    TEMPLATES[key]['note']+='\n源模板：'+source

from .template_store import load_library
load_library(TEMPLATES)
MAX_SLOTS = max(len(value['slots']) for value in TEMPLATES.values())
