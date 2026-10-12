#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

FFMPEG=Path(sys.argv[1]).resolve()
HOME=Path(sys.argv[2]).resolve()
assert FFMPEG.is_file(),FFMPEG
app_data=HOME/'Library'/'Application Support'/'studio.endlume.desktop'
assets=app_data/'Library'/'QA-10.0.14'
assets.mkdir(parents=True,exist_ok=True)


def run(args):
    subprocess.run([str(x) for x in args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)


def make_video(path,filters,duration=4):
    # Real persisted MP4 asset: 640x360, 60 fps, green key background.
    run([
      FFMPEG,'-hide_banner','-loglevel','error',
      '-f','lavfi','-i',f'color=c=0x00ff00:s=640x360:r=60:d={duration}',
      '-vf',filters,'-an','-c:v','mpeg4','-q:v','2','-pix_fmt','yuv420p','-r','60','-y',path
    ])
    assert path.is_file() and path.stat().st_size>1024,path


eq_src=assets/'round-equalizer.mp4'
film_src=assets/'80s-film.mp4'
sub_src=assets/'subscribe.mp4'

# Broad visible bars for the equalizer. The green field is removed by chromakey.
make_video(eq_src,
  "drawbox=x=90:y=90:w=42:h=190:color=white@1:t=fill,"
  "drawbox=x=150:y=130:w=42:h=150:color=red@1:t=fill,"
  "drawbox=x=210:y=65:w=42:h=215:color=cyan@1:t=fill,"
  "drawbox=x=270:y=115:w=42:h=165:color=yellow@1:t=fill,"
  "drawbox=x=330:y=45:w=42:h=235:color=magenta@1:t=fill,"
  "drawbox=x=390:y=105:w=42:h=175:color=blue@1:t=fill,"
  "drawbox=x=450:y=75:w=42:h=205:color=white@1:t=fill")

# Sparse but high-contrast ordinary effect, matching the 80s-film acceptance shape.
make_video(film_src,
  "drawbox=x=70:y=55:w=16:h=16:color=white@1:t=fill,"
  "drawbox=x=180:y=245:w=12:h=12:color=yellow@1:t=fill,"
  "drawbox=x=310:y=120:w=18:h=8:color=white@1:t=fill,"
  "drawbox=x=470:y=205:w=14:h=14:color=red@1:t=fill,"
  "drawbox=x=555:y=80:w=10:h=22:color=white@1:t=fill")

# Real Subscribe asset with broad visible coverage.
make_video(sub_src,
  "drawbox=x=120:y=105:w=400:h=150:color=red@1:t=fill,"
  "drawbox=x=165:y=135:w=310:h=90:color=white@1:t=fill,"
  "drawbox=x=205:y=160:w=230:h=40:color=blue@1:t=fill")


def effect(effect_id,name,source,*,x=.5,y=.5,scale=.34):
    return {
      'id':effect_id,'name':name,'source':str(source),'enabled':True,'mode':'chromakey',
      'keyColor':'#00ff00','similarity':0.10,'blend':0.06,'despill':0.35,
      'lumaThreshold':0.03,'lumaTolerance':0.08,'saturation':1.0,
      'x':x,'y':y,'scale':scale,'fullscreen':False,'previewFrameTime':0.0,
      'startSec':0.0,'endSec':None,'cacheKey':None,'cacheReady':False,
      'usageMode':'always','intervalSec':240.0,'usageDurationSec':30.0,
      'target':'CUSTOM','offsetX':0.0,'offsetY':0.0,'opacity':1.0,
      'assetState':'ready'
    }

round_eq=effect('825dd7a4-f0cf-4032-a3c9-64290cb5756d','Эквалайзер круглый',eq_src,scale=.46)
film=effect('qa-1014-80s-film','80s Film Dust',film_src,x=.36,y=.36,scale=.45)
subscribe=effect('qa-1014-subscribe','Subscribe QA 10.0.14',sub_src,x=.5,y=.68,scale=.52)
subscribe.update({
  'usageMode':'interval','intervalSec':240.0,'usageDurationSec':8.0,
  'firstAtSec':0.0,'secondAtSec':240.0,'repeatEverySec':240.0,
  'firstAppearance':'immediate','customFirstAtSec':0.0,'showDurationSec':8.0
})

payload={
  'effects':[round_eq,film],
  'subscribes':[subscribe],
  'ambient':None,
  'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}
}
library=app_data/'library.json'
library.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
assert library.is_file()
print(f'QA_HOME={HOME}')
print(f'QA_LIBRARY={library}')
print('PERSISTED_ROUND_EQUALIZER=GREEN')
print('PERSISTED_80S_EFFECT=GREEN')
print('PERSISTED_SUBSCRIBE=GREEN')
