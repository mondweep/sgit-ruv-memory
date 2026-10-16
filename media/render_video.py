"""Render an evidence-driven walkthrough and compose an original upbeat soundtrack."""
import json,math,subprocess,wave
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
W,H,FPS=1280,720,24
DURATION=64
FONT='/usr/share/fonts/truetype/dejavu/'
def font(n,bold=False,mono=False):return ImageFont.truetype(FONT+('DejaVuSansMono.ttf' if mono else 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),n)
events=json.loads((ROOT/'evidence/demo-events.json').read_text())
c=next(e['details'] for e in events if e['step']=='Encrypted checkpoint committed');short=c['ciphertext_sha256'][:24]
scenes=[
 ('Memory that survives the run','SGit × rUv Memory','A local MCP server. Encrypted checkpoints. Verified recovery.', ['REAL MCP RUN','SQLITE BACKUP','SGIT VAULTS'], 'A working local MVP — built and tested'),
 ('01 / Connect','One interface. Four tools.','The client connects to the real MCP server over stdio.', ['checkpoint(namespace)','inspect(checkpoint_id)','restore(checkpoint_id, workspace)','close_run(checkpoint_id)'], 'Host configuration fixes identity and allowed databases'),
 ('02 / Apply policy','Permission comes first.','An ABP mandate compiles into Ruflo rules before each operation.', ['namespace: forbidden','decision: DENIED','checkpoint files created: 0'], 'A denied namespace creates no checkpoint'),
 ('03 / Capture','Two facts. One consistent snapshot.','SQLite backup captures committed data, including WAL writes.', ['coder  → consistent snapshots','tester → verify before promotion','PRAGMA integrity_check → ok'], 'Two role-labelled sample facts in a SQLite memory fixture'),
 ('04 / Encrypt','A real SGit vault commit.','Only the encrypted bare store leaves private staging.', ['AES-256-GCM via SGit 0.22.3','vault keys → separate private directory','ciphertext SHA-256: '+short+'…'], 'Plaintext fragment hits: 0 • key marker hits: 0'),
 ('05 / Recover','Remove the source. Start fresh.','The demo removes the original database and restarts MCP.', ['original database exists: false','new MCP server process: connected','restore → fresh-runner'], 'Recovery uses the saved checkpoint and its private key record'),
 ('06 / Verify','Both facts are back.','Decrypt, verify the digest, check SQLite, then promote.', ['restored rows: 2 / 2','database SHA-256: MATCH','existing workspace: never overwritten'], 'Restore succeeds in an isolated workspace'),
 ('07 / Challenge','Tampering stops here.','The demo alters stored bytes, then tries another restore.', ['ciphertext integrity: MISMATCH','restore: BLOCKED','tampered workspace created: false'], 'Sixteen tests also pass, including live writes and wrong keys'),
]
# Original instrumental: 120 BPM, four-on-the-floor drums, warm chords, plucked melody.
sr=44100;n=int(sr*DURATION);music=np.zeros(n,dtype=np.float64);rng=np.random.default_rng(73)
def add(at,sound,gain=1):
 i=int(at*sr);end=min(n,i+len(sound))
 if i<n:music[i:end]+=sound[:end-i]*gain
def note(at,midi,dur,gain=.12):
 t=np.arange(int(sr*dur))/sr;f=440*2**((midi-69)/12);env=(1-np.exp(-t*70))*np.exp(-t*4/dur)
 add(at,(np.sin(2*np.pi*f*t)+.18*np.sin(4*np.pi*f*t))*env,gain)
chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]]
for beat in range(DURATION*2):
 at=beat*.5;t=np.arange(int(sr*.28))/sr
 kick=np.sin(2*np.pi*(48*t+65*.025*(1-np.exp(-t/.025))))*np.exp(-t*20);add(at,kick,.35)
 if beat%2==1:
  t=np.arange(int(sr*.15))/sr;add(at,rng.normal(0,1,len(t))*np.exp(-t*35),.08)
 for off in [0,.25]:
  t=np.arange(int(sr*.06))/sr;noise=rng.normal(0,1,len(t));noise=np.concatenate([[0],np.diff(noise)]);add(at+off,noise*np.exp(-t*90),.025)
 chord=chords[(beat//4)%4]
 if beat%4==0:
  for m in chord:note(at,m,1.8,.07)
 note(at,chord[0]-12,.38,.17)
 melody=[0,2,1,2,0,1,2,1][beat%8];note(at+.25,chord[melody]+12,.30,.09)
music=np.tanh(music)*.65
fade=np.minimum(1,np.arange(n)/sr/1.5)*np.minimum(1,(n-np.arange(n))/sr/2.5);music*=fade
stereo=np.stack([music,np.roll(music,400)*.95],axis=1)
with wave.open(str(ROOT/'media/music.wav'),'wb') as f:f.setnchannels(2);f.setsampwidth(2);f.setframerate(sr);f.writeframes((stereo*32767).astype('<i2').tobytes())
cmd=['ffmpeg','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-i',str(ROOT/'media/music.wav'),'-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-af','volume=6dB','-c:a','aac','-b:a','192k','-movflags','+faststart','-shortest',str(ROOT.parent/'SGit-rUv-Memory-MVP.mp4')]
p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=open(ROOT/'media/render.log','w'))
for frame in range(DURATION*FPS):
 t=frame/FPS;idx=min(7,int(t//8));local=t%8;tag,title,subtitle,lines,caption=scenes[idx]
 im=Image.new('RGB',(W,H),(9,16,30));d=ImageDraw.Draw(im)
 for x in range(0,W,64):d.line((x,0,x,H),fill=(15,26,43))
 for y in range(0,H,64):d.line((0,y,W,y),fill=(15,26,43))
 d.rounded_rectangle((48,38,240,76),radius=16,fill=(19,54,62));d.text((64,46),'SGIT × RUV',font=font(19,True),fill=(92,239,208))
 d.text((970,48),'LOCAL MVP / 0.2',font=font(17,True),fill=(146,165,189))
 d.text((64,111),tag.upper(),font=font(19,True),fill=(78,219,193))
 d.text((60,152),title,font=font(46,True),fill=(242,247,255))
 d.text((64,222),subtitle,font=font(22),fill=(165,185,211))
 d.rounded_rectangle((64,282,1216,550),radius=24,fill=(17,31,50),outline=(37,66,88),width=2)
 for j,line in enumerate(lines):
  if local>j*.6:
   y=313+j*51;d.ellipse((91,y+7,103,y+19),fill=(79,226,190));d.text((122,y),line,font=font(23,mono=True),fill=(218,235,249))
 d.rounded_rectangle((64,575,1216,638),radius=15,fill=(21,46,57));d.text((86,594),caption,font=font(21),fill=(186,240,226))
 d.text((64,666),'Evidence-driven walkthrough • no voiceover',font=font(17),fill=(119,145,172))
 for j in range(8):
  x=822+j*49;d.rounded_rectangle((x,672,x+37,677),radius=2,fill=(73,224,190) if j<=idx else (44,61,79))
 d.rectangle((0,H-5,int(W*t/DURATION),H),fill=(79,226,190))
 # Gentle fade-in per scene.
 if local<.28:im=Image.blend(Image.new('RGB',(W,H),(9,16,30)),im,local/.28)
 if frame==5*FPS+12:im.save(ROOT/'media/preview.png')
 p.stdin.write(im.tobytes())
p.stdin.close();assert p.wait()==0
# Portable subtitle companion as well as burned-in text.
with open(ROOT/'media/captions.srt','w') as f:
 for i,s in enumerate(scenes):
  def stamp(sec):return f'00:{sec//60:02}:{sec%60:02},000'
  f.write(f'{i+1}\n{stamp(i*8)} --> {stamp((i+1)*8)}\n{s[1]}\n{s[2]}\n\n')
print('Rendered',ROOT.parent/'SGit-rUv-Memory-MVP.mp4')
