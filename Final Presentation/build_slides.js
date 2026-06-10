const pptxgen = require("pptxgenjs");
const fs = require("fs");

// ============ palette ============
const CHAR  = "343734";   // primary dark bg + dark text
const BLUE  = "70A1BD";   // accent
const CREAM = "EFF1E8";   // light bg / light text
const CARD  = "40433E";   // lighter card on charcoal
const CARDB = "4E514B";   // card hairline / muted
const PANEL = "2C2F2B";   // darker panel/code on charcoal
const WHITE = "FFFFFF";
const MUT_D = "9BA29C";    // muted text on dark
const RED   = "C26B5E";    // problem tag
const GREEN = "8FBF9F";    // positive

// ============ fonts ============
const FZH   = "Microsoft JhengHei";
const FBLK  = "Arial Black";
const FMONO = "Consolas";

const FIG = "/sessions/jolly-youthful-hypatia/mnt/Final Presentation/figures";
const DIMS = {
  fig01:[924,597], fig02:[966,601], fig03:[1494,642], fig04:[1191,717],
  fig05:[1186,717], fig06:[1205,834], fig07:[1261,618], fig08:[940,602],
  fig09:[801,717], fig10:[801,717], fig11:[629,619], fig12:[917,602],
  fig13:[1266,642], fig14:[796,718], fig15:[796,602], fig16:[1266,642],
  fig17:[920,863]
};

const pres = new pptxgen();
pres.defineLayout({ name: "BIG", width: 20, height: 11.25 });
pres.layout = "BIG";
pres.author = "阿維";
pres.title = "YouTube 影片早期成長與爆紅預測";
const W = 20, H = 11.25;

// ============ speaker notes ============
const csv = fs.readFileSync("/sessions/jolly-youthful-hypatia/mnt/Final Presentation/slide_plan.csv","utf8");
function parseCSV(t){const rows=[];let f="",row=[],q=false;for(let i=0;i<t.length;i++){const c=t[i];if(q){if(c=='"'){if(t[i+1]=='"'){f+='"';i++;}else q=false;}else f+=c;}else{if(c=='"')q=true;else if(c==','){row.push(f);f="";}else if(c=='\n'){row.push(f);rows.push(row);row=[];f="";}else if(c=='\r'){}else f+=c;}}if(f.length||row.length){row.push(f);rows.push(row);}return rows;}
const allRows = parseCSV(csv.replace(/^﻿/,""));
const head = allRows[0]; const NOTES={};
for(let i=1;i<allRows.length;i++){const r=allRows[i];if(r[0])NOTES[r[0]]=r[head.indexOf("speaker_notes")]||"";}

// ============ helpers ============
const sh = () => ({ type:"outer", color:"000000", blur:9, offset:3, angle:120, opacity:0.28 });
function slide(bg){ const s=pres.addSlide(); s.background={color:bg}; return s; }
function notes(s,n){ if(NOTES[n]) s.addNotes(NOTES[n]); }

// title + optional gray subtitle line
function header(s, ttl, sub, onDark){
  const tc = onDark?CREAM:CHAR;
  s.addText(ttl,{x:0.9,y:0.5,w:18.2,h:0.95,fontSize:36,bold:true,color:tc,fontFace:FZH,align:"left",valign:"middle",margin:0});
  if(sub) s.addText(sub,{x:0.95,y:1.42,w:18,h:0.55,fontSize:19,italic:true,color:onDark?MUT_D:"6E746C",fontFace:FZH,align:"left",margin:0});
}
function rrect(s,x,y,w,h,fill,opt={}){
  s.addShape(pres.shapes.ROUNDED_RECTANGLE,Object.assign({x,y,w,h,fill:{color:fill},rectRadius:opt.r??0.1},opt.line?{line:opt.line}:{}, opt.shadow?{shadow:sh()}:{}));
}
// stat callout
function stat(s,x,y,w,h,num,label,opt={}){
  const cardFill = opt.fill || CARD;
  rrect(s,x,y,w,h,cardFill,{r:0.1,shadow:opt.shadow!==false});
  s.addShape(pres.shapes.RECTANGLE,{x,y,w:0.14,h,fill:{color:opt.accent||BLUE}});
  s.addText(num,{x:x+0.3,y:y+0.18,w:w-0.5,h:h*0.6,fontSize:opt.numSize||52,bold:true,color:opt.numColor||(opt.dark?CREAM:CHAR),fontFace:FBLK,align:"left",valign:"middle",margin:0});
  s.addText(label,{x:x+0.34,y:y+h*0.62,w:w-0.5,h:h*0.34,fontSize:opt.labelSize||18,color:opt.labelColor||(opt.dark?MUT_D:"6E746C"),fontFace:FZH,align:"left",valign:"middle",margin:0});
}
// small tag
function tag(s,x,y,text,fill,tc){
  const w = 0.42 + text.length*0.28;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE,{x,y,w,h:0.5,fill:{color:fill},rectRadius:0.06});
  s.addText(text,{x,y,w,h:0.5,fontSize:18,bold:true,color:tc||CREAM,fontFace:FZH,align:"center",valign:"middle",margin:0});
  return w;
}
// circle number badge
function badge(s,x,y,d,text,fill,tc){
  s.addShape(pres.shapes.OVAL,{x,y,w:d,h:d,fill:{color:fill}});
  s.addText(text,{x,y,w:d,h:d,fontSize:d*30,bold:true,color:tc||CREAM,fontFace:FBLK,align:"center",valign:"middle",margin:0});
}
function arrow(s,x,y,w,h,color){
  s.addShape(pres.shapes.LINE,{x,y,w,h,line:{color,width:3,endArrowType:"triangle"}});
}
function fitImage(s, file, box){
  const key=file.match(/fig\d+/)[0]; const d=DIMS[key]; const ar=d[0]/d[1];
  let w=box.w,h=w/ar; if(h>box.h){h=box.h;w=h*ar;}
  const x=box.x+(box.w-w)/2, y=box.y+(box.h-h)/2;
  // white frame behind
  s.addShape(pres.shapes.RECTANGLE,{x:x-0.12,y:y-0.12,w:w+0.24,h:h+0.24,fill:{color:WHITE},shadow:sh()});
  s.addImage({path:`${FIG}/${file.split("/").pop()}`,x,y,w,h});
  return {x,y,w,h};
}

// ====================================================================
// SLIDE 1 — cover (charcoal, premium)
// ====================================================================
let s = slide(CHAR);
// YouTube play button motif top-right
s.addShape(pres.shapes.ROUNDED_RECTANGLE,{x:17.0,y:0.85,w:2.0,h:1.4,fill:{color:RED},rectRadius:0.28});
s.addShape("triangle",{x:17.7,y:1.28,w:0.62,h:0.55,fill:{color:WHITE},rotate:90});
// growth curve bottom
const cv=[[10.5,9.9],[12.2,9.4],[13.8,8.9],[15.2,8.0],[16.5,6.5],[17.7,4.6],[18.7,2.6]];
for(let i=0;i<cv.length-1;i++) s.addShape(pres.shapes.LINE,{x:cv[i][0],y:cv[i][1],w:cv[i+1][0]-cv[i][0],h:cv[i+1][1]-cv[i][1],line:{color:BLUE,width:3}});
s.addShape(pres.shapes.OVAL,{x:18.5,y:2.4,w:0.4,h:0.4,fill:{color:RED}});
s.addText([{text:"YouTube",options:{fontFace:FBLK,color:CREAM}},{text:" 影片早期成長",options:{fontFace:FZH,color:CREAM}}],
  {x:0.95,y:3.0,w:15,h:1.5,fontSize:66,bold:true,align:"left",valign:"middle",margin:0});
s.addText("與爆紅預測",{x:0.95,y:4.55,w:15,h:1.5,fontSize:66,bold:true,color:CREAM,fontFace:FZH,align:"left",valign:"middle",margin:0});
s.addShape(pres.shapes.RECTANGLE,{x:1.0,y:6.35,w:0.16,h:0.95,fill:{color:BLUE}});
s.addText("3 小時資料能預測 48 小時爆紅嗎？",{x:1.35,y:6.3,w:15,h:1.0,fontSize:28,color:BLUE,fontFace:FZH,bold:true,valign:"middle",margin:0});
s.addText("資料探勘導論　·　2026 期末專題",{x:1.0,y:8.7,w:15,h:0.6,fontSize:20,color:MUT_D,fontFace:FZH,margin:0});
notes(s,"1");

// ====================================================================
// SLIDE 2 — 7x gap hook (blue accent slide)
// ====================================================================
s = slide(BLUE);
s.addText("同樣在 3 小時前發布——",{x:0.9,y:0.7,w:18.2,h:0.9,fontSize:32,bold:true,color:CREAM,fontFace:FZH,align:"center",margin:0});
// two cards
rrect(s,1.6,2.3,7.6,6.0,CHAR,{r:0.12,shadow:true});
rrect(s,10.8,2.3,7.6,6.0,CHAR,{r:0.12,shadow:true});
s.addShape(pres.shapes.RECTANGLE,{x:10.8,y:2.3,w:7.6,h:0.18,fill:{color:RED}});
s.addText("Non-viral",{x:1.6,y:2.7,w:7.6,h:0.7,fontSize:24,color:MUT_D,fontFace:FZH,align:"center",margin:0});
s.addText("184",{x:1.6,y:3.4,w:7.6,h:3.4,fontSize:150,bold:true,color:CREAM,fontFace:FBLK,align:"center",valign:"middle",transparency:30,margin:0});
s.addText("3 小時觀看數",{x:1.6,y:7.0,w:7.6,h:0.7,fontSize:20,color:MUT_D,fontFace:FZH,align:"center",margin:0});
s.addText("Viral",{x:10.8,y:2.7,w:7.6,h:0.7,fontSize:24,bold:true,color:RED,fontFace:FZH,align:"center",margin:0});
s.addText("1,312",{x:10.8,y:3.4,w:7.6,h:3.4,fontSize:150,bold:true,color:CREAM,fontFace:FBLK,align:"center",valign:"middle",margin:0});
s.addText("3 小時觀看數",{x:10.8,y:7.0,w:7.6,h:0.7,fontSize:20,color:MUT_D,fontFace:FZH,align:"center",margin:0});
s.addText("vs",{x:9.2,y:4.5,w:1.6,h:1.4,fontSize:44,italic:true,bold:true,color:CREAM,fontFace:FZH,align:"center",valign:"middle",margin:0});
s.addText([{text:"7 倍",options:{bold:true,fontSize:40}},{text:" 的差距，在第 3 小時就已經出現——能被預測嗎？",options:{}}],
  {x:1.6,y:8.7,w:16.8,h:1.2,fontSize:28,italic:true,color:CREAM,fontFace:FZH,align:"center",valign:"middle",margin:0});
notes(s,"2");

// ====================================================================
// SLIDES 3 & 4 — two prediction tasks (charcoal, dark cards) on ONE pattern
// ====================================================================
function taskSlide(no,ttl,sub,tagTxt,io,viralLine,tl){
  const s=slide(CREAM); header(s,ttl,sub,false);
  rrect(s,0.9,2.2,11.0,6.3,WHITE,{r:0.1,shadow:true});
  tag(s,1.3,2.6,tagTxt,CHAR,CREAM);
  s.addText(io,{x:1.3,y:3.6,w:10.2,h:3.0,fontSize:24,color:CHAR,fontFace:FZH,valign:"top",lineSpacingMultiple:1.5,margin:0});
  // viral stat inside
  s.addShape(pres.shapes.LINE,{x:1.3,y:6.7,w:10.2,h:0,line:{color:"D5D8CF",width:1.5}});
  s.addText(viralLine,{x:1.3,y:6.85,w:10.2,h:1.4,fontSize:22,color:CHAR,fontFace:FZH,valign:"middle",lineSpacingMultiple:1.2,margin:0});
  // timeline card on right
  rrect(s,12.3,2.2,6.8,6.3,CHAR,{r:0.1,shadow:true});
  s.addText("時間軸",{x:12.7,y:2.55,w:6,h:0.6,fontSize:20,color:MUT_D,fontFace:FZH,margin:0});
  const tx=12.9,tw=5.6,ty=5.3;
  s.addShape(pres.shapes.LINE,{x:tx,y:ty,w:tw,h:0,line:{color:CARDB,width:2}});
  const segEnd=tx+tw*tl.f;
  s.addShape(pres.shapes.LINE,{x:tx,y:ty,w:tw*tl.f,h:0,line:{color:BLUE,width:10}});
  s.addShape(pres.shapes.LINE,{x:segEnd,y:ty,w:tx+tw-segEnd,h:0,line:{color:MUT_D,width:2,dashType:"dash"}});
  tl.marks.forEach(m=>{const mx=tx+tw*m.f;
    s.addShape(pres.shapes.OVAL,{x:mx-0.12,y:ty-0.12,w:0.24,h:0.24,fill:{color:m.f<=tl.f?BLUE:CREAM}});
    s.addText(m.t,{x:mx-1.1,y:ty+0.25,w:2.2,h:0.9,fontSize:17,bold:true,color:CREAM,fontFace:FZH,align:"center",lineSpacingMultiple:0.95,margin:0});
  });
  s.addText("輸入範圍",{x:tx,y:ty-0.75,w:tw*tl.f,h:0.5,fontSize:16,bold:true,color:BLUE,fontFace:FZH,align:"center",margin:0});
  notes(s,no);
}
taskSlide("3","任務一：3 小時預測 48 小時爆紅","發布後極早期的訊號，能否預判爆紅？","分類（二元）",
  [{text:"輸入　",options:{bold:true,color:BLUE}},{text:"影片發布後 ",options:{}},{text:"0–3 小時",options:{bold:true}},{text:"的資料",options:{breakLine:true}},
   {text:"輸出　",options:{bold:true,color:BLUE}},{text:"48 小時內是否達到",options:{}},{text:"爆紅門檻",options:{bold:true}},{text:"？",options:{}}],
  [{text:"病毒率　",options:{color:"6E746C"}},{text:"12.6%",options:{bold:true,fontSize:34,color:CHAR}},{text:"　（1,916 支中 241 支爆紅）",options:{color:"6E746C"}}],
  {f:0.45,marks:[{f:0,t:"0h"},{f:0.45,t:"3h"},{f:1,t:"48h\n標籤"}]});
taskSlide("4","任務二：48 小時預測未來 24 小時成長","已知前兩天的軌跡，能否預估後續動能？","迴歸（連續值）",
  [{text:"輸入　",options:{bold:true,color:BLUE}},{text:"影片發布後 ",options:{}},{text:"0–48 小時",options:{bold:true}},{text:"的資料",options:{breakLine:true}},
   {text:"輸出　",options:{bold:true,color:BLUE}},{text:"log（第 48–72 小時新增觀看數）",options:{bold:true}}],
  [{text:"樣本數　",options:{color:"6E746C"}},{text:"2,394 筆",options:{bold:true,fontSize:34,color:CHAR}}],
  {f:0.667,marks:[{f:0,t:"0h"},{f:0.667,t:"48h"},{f:1,t:"72h\n標籤"}]});

// ====================================================================
// divider helper (premium charcoal)
// ====================================================================
function divider(num,name,items,no){
  const s=slide(CHAR);
  // ghost big number
  s.addText(num,{x:9.5,y:0.5,w:11,h:11,fontSize:560,bold:true,color:CARD,fontFace:FBLK,align:"right",valign:"middle",margin:0});
  s.addShape(pres.shapes.RECTANGLE,{x:1.0,y:3.5,w:0.18,h:2.2,fill:{color:BLUE}});
  s.addText("CHAPTER",{x:1.4,y:3.4,w:8,h:0.6,fontSize:22,bold:true,color:BLUE,fontFace:FBLK,charSpacing:4,margin:0});
  s.addText(num,{x:1.35,y:3.85,w:9,h:2.0,fontSize:130,bold:true,color:CREAM,fontFace:FBLK,valign:"middle",margin:0});
  s.addText(name,{x:1.4,y:6.0,w:12,h:1.3,fontSize:56,bold:true,color:CREAM,fontFace:FZH,margin:0});
  if(items) s.addText(items,{x:1.45,y:7.5,w:12,h:0.8,fontSize:22,color:MUT_D,fontFace:FZH,margin:0});
  notes(s,no);
}

// ====================================================================
// figure slide helper — figure + insight panel (auto layout by aspect)
// ====================================================================
function figRows(items){
  const arr=[];
  items.forEach((it,i)=>{
    if(typeof it==="string"){ arr.push({text:it,options:{bullet:{code:"25AA"},color:CREAM,breakLine:true,paraSpaceAfter:10}}); }
    else { arr.push({text:it.h+"\n",options:{bullet:{code:"25AA"},bold:true,color:BLUE,breakLine:true}});
           arr.push({text:it.d,options:{indentLevel:1,color:CREAM,breakLine:true,paraSpaceAfter:12}}); }
  });
  return arr;
}
function figureSlide(no,ttl,sub,file,items,onDark,bottomLine){
  const bgc = onDark?CHAR:CREAM;
  const s=slide(bgc); header(s,ttl,sub,onDark);
  const key=file.match(/fig\d+/)[0]; const ar=DIMS[key][0]/DIMS[key][1];
  const tc=onDark?CREAM:CHAR;
  if(ar>=1.75){
    // wide figure on top, insight strip below
    fitImage(s,file,{x:0.9,y:2.0,w:18.2,h:6.3});
    rrect(s,0.9,8.6,18.2,2.1,onDark?CARD:WHITE,{r:0.1,shadow:true});
    s.addShape(pres.shapes.RECTANGLE,{x:0.9,y:8.6,w:0.14,h:2.1,fill:{color:BLUE}});
    s.addText("看點",{x:1.25,y:8.78,w:2,h:0.5,fontSize:18,bold:true,color:BLUE,fontFace:FZH,margin:0});
    s.addText(figRows(items),{x:1.25,y:9.25,w:17.4,h:1.3,fontSize:20,color:tc,fontFace:FZH,valign:"top",margin:0});
  } else {
    // figure left, insight panel right
    fitImage(s,file,{x:0.9,y:2.0,w:11.7,h:8.6});
    rrect(s,12.9,2.0,6.2,8.6,onDark?CARD:WHITE,{r:0.1,shadow:true});
    s.addShape(pres.shapes.RECTANGLE,{x:12.9,y:2.0,w:0.14,h:8.6,fill:{color:BLUE}});
    s.addText("看這張圖",{x:13.3,y:2.35,w:5.4,h:0.6,fontSize:22,bold:true,color:BLUE,fontFace:FZH,margin:0});
    s.addText(figRows(items),{x:13.3,y:3.15,w:5.5,h:6.8,fontSize:22,color:tc,fontFace:FZH,valign:"top",lineSpacingMultiple:1.15,margin:0});
    if(bottomLine) s.addText(bottomLine,{x:13.3,y:9.4,w:5.5,h:1.0,fontSize:22,bold:true,italic:true,color:tc,fontFace:FZH,valign:"bottom",margin:0});
  }
  notes(s,no);
}

// ====================================================================
// SLIDE 5 — divider 02
// ====================================================================
divider("02","資料蒐集","爬蟲架構　·　蒐集規模　·　Shorts 偵測　·　資料樣貌","5");

// ====================================================================
// SLIDE 6 — three-layer data structure (charcoal, 3 cards)
// ====================================================================
s = slide(CHAR); header(s,"爬蟲蒐集了什麼：三層資料結構","靜態、時序、留言三種粒度的資料同時追蹤",true);
const L6=[
  ["01","靜態資訊","一次性","標題　·　類別\n頻道訂閱數\n發布時間\nShorts / Long"],
  ["02","時序快照","多次追蹤","0h / 1h / 3h /\n48h / 72h 的\n觀看 · 按讚 ·\n留言數"],
  ["03","留言快照","0–3h 以內","每則留言的：\n文字內容\n發布時間\n按讚數"],
];
L6.forEach((c,i)=>{
  const x=0.9+i*6.15, w=5.8;
  rrect(s,x,2.4,w,8.0,CARD,{r:0.1,shadow:true});
  badge(s,x+0.45,2.85,1.0,c[0],BLUE,CREAM);
  s.addText(c[1],{x:x+1.65,y:2.9,w:w-1.8,h:0.6,fontSize:28,bold:true,color:CREAM,fontFace:FZH,valign:"middle",margin:0});
  s.addText(c[2],{x:x+1.65,y:3.5,w:w-1.8,h:0.5,fontSize:18,color:BLUE,fontFace:FZH,margin:0});
  s.addShape(pres.shapes.LINE,{x:x+0.45,y:4.35,w:w-0.9,h:0,line:{color:CARDB,width:1.5}});
  s.addText(c[3],{x:x+0.55,y:4.6,w:w-1.0,h:5.4,fontSize:23,color:CREAM,fontFace:FZH,valign:"top",lineSpacingMultiple:1.4,margin:0});
  if(i<2) arrow(s,x+w+0.05,6.4,0.25,0,BLUE);
});
notes(s,"6");

// ====================================================================
// SLIDE 7 — four key numbers (cream, 4 stat cards)
// ====================================================================
s = slide(CREAM); header(s,"蒐集規模：四個關鍵數字","從零蒐集到具規模的時序資料集",false);
const N7=[["1,916","分類樣本數"],["2,394","迴歸樣本數"],["33,895","時序觀測 rows"],["642","有留言情緒的影片"]];
N7.forEach((n,i)=>{ stat(s,0.9+i*4.6,3.6,4.2,3.6,n[0],n[1],{numSize:60,labelSize:22,dark:true}); });
s.addText("跨越多元類別、Shorts 與長影片並存，並具備逐時的成長軌跡與早期留言。",
  {x:0.9,y:8.2,w:18.2,h:0.8,fontSize:22,italic:true,color:"6E746C",fontFace:FZH,align:"center",margin:0});
notes(s,"7");

// ====================================================================
// SLIDE 8 — Shorts detection (charcoal, code + uses)
// ====================================================================
s = slide(CHAR); header(s,"Shorts 偵測：用 HTTP 狀態碼判斷","一次請求即可區分短影音與長影片",true);
rrect(s,0.9,2.4,9.0,8.0,PANEL,{r:0.1});
s.addText("判斷邏輯",{x:1.3,y:2.7,w:8,h:0.6,fontSize:20,color:MUT_D,fontFace:FZH,margin:0});
s.addText([
  {text:"GET /shorts/{video_id}",options:{bold:true,breakLine:true,fontSize:26,color:CREAM}},
  {text:" ",options:{breakLine:true,fontSize:14}},
  {text:"├─ HTTP 200  →  ",options:{color:CREAM}},{text:"Shorts ✓",options:{bold:true,color:GREEN,breakLine:true}},
  {text:"└─ HTTP 303  →  ",options:{color:CREAM}},{text:"長影片",options:{bold:true,color:BLUE,breakLine:true}},
  {text:"        （redirect → /watch）",options:{fontSize:19,color:MUT_D}},
],{x:1.3,y:3.5,w:8.2,h:4.0,fontFace:FMONO,valign:"top",lineSpacingMultiple:1.4,margin:0});
s.addText([{text:"爆紅門檻　",options:{bold:true,color:BLUE}},{text:"Shorts 最低 10,000　·　長影片 2,000",options:{color:CREAM}}],
  {x:1.3,y:8.7,w:8.2,h:1.2,fontSize:21,fontFace:FZH,valign:"middle",lineSpacingMultiple:1.2,margin:0});
const U8=[["作為模型特徵","is_shorts 直接成為預測欄位"],["資料切分依據","Shorts / 長影片分組切分"],["門檻計算依據","不同類型套用不同爆紅標準"]];
U8.forEach((u,i)=>{
  const y=2.6+i*2.65;
  rrect(s,10.4,y,8.7,2.4,CARD,{r:0.1,shadow:true});
  badge(s,10.8,y+0.7,1.0,String(i+1),BLUE,CREAM);
  s.addText(u[0],{x:12.1,y:y+0.5,w:6.7,h:0.7,fontSize:25,bold:true,color:CREAM,fontFace:FZH,margin:0});
  s.addText(u[1],{x:12.1,y:y+1.25,w:6.7,h:0.8,fontSize:21,color:MUT_D,fontFace:FZH,margin:0});
});
notes(s,"8");

// ====================================================================
// SLIDE 9 — discovery delay (cream, big stat + 3 cards + supplementary)
// ====================================================================
s = slide(CREAM); header(s,"最大的挑戰：發現延遲讓 99% 的資料無法使用","爬到影片時，0–3h 視窗往往已經錯過",false);
// big stat strip
rrect(s,0.9,2.05,18.2,1.5,CHAR,{r:0.1,shadow:true});
s.addText([
  {text:"10,238",options:{bold:true,color:CREAM}},{text:"  支爬取   →   ",options:{color:MUT_D,fontSize:30}},
  {text:"202",options:{bold:true,color:BLUE}},{text:"  支可用   ",options:{color:MUT_D,fontSize:30}},
  {text:"（僅 1.97%）",options:{color:RED,fontSize:34,bold:true}},
],{x:1,y:2.05,w:18,h:1.5,fontSize:50,fontFace:FBLK,align:"center",valign:"middle",margin:0});
const C9=[["問題",RED,"爬了 10,238 支影片，只有 202 支有 0–3h 完整資料"],
          ["原因",CHAR,"影片被發現時平均已發布 30 分鐘，0–3h 視窗已錯過"],
          ["解法",BLUE,"改用 fresh_search，本地過濾只追蹤 ≤5 分鐘前發布者"]];
C9.forEach((c,i)=>{
  const x=0.9+i*6.15, w=5.8;
  rrect(s,x,3.95,w,2.95,WHITE,{r:0.1,shadow:true});
  tag(s,x+0.35,4.25,c[0],c[1],CREAM);
  s.addText(c[2],{x:x+0.4,y:5.0,w:w-0.8,h:1.7,fontSize:22,color:CHAR,fontFace:FZH,valign:"top",lineSpacingMultiple:1.25,margin:0});
});
// supplementary dark card grid
rrect(s,0.9,7.15,18.2,3.3,CHAR,{r:0.1,shadow:true});
s.addText("其他工程挑戰",{x:1.3,y:7.35,w:8,h:0.55,fontSize:20,bold:true,color:BLUE,fontFace:FZH,margin:0});
const SUP=[["YouTube API 持續改版","改用 InnerTube 介面"],["雙 Scheduler 互相覆寫","加 PID 隔離寫入"],["_sleep race condition","爬蟲靜默停擺 10 小時"]];
SUP.forEach((p,i)=>{
  const x=1.3+i*6.0;
  s.addText([{text:p[0]+"\n",options:{bold:true,color:CREAM,breakLine:true}},{text:p[1],options:{color:MUT_D}}],
    {x,y:7.95,w:5.6,h:2.2,fontSize:20,fontFace:FZH,valign:"top",lineSpacingMultiple:1.25,margin:0});
});
notes(s,"9");

// ====================================================================
// SLIDES 10,11,12 — figures
// ====================================================================
figureSlide("10","影片類別分布","Top-10 類別，分布多元而非單一題材","fig04_category_distribution.png",
  ["Entertainment 佔最大宗","其後為 Gaming、People & Blogs、Music","題材涵蓋多元，非單一類型"],false,"涵蓋多元類別");
figureSlide("11","Viral vs Non-viral 的成長軌跡完全不同","兩群影片在極早期就分道揚鑣","fig05_growth_curve_examples.png",
  [{h:"3h 之前已分歧",d:"藍／紅曲線在 3 小時前就明顯拉開"},{h:"3h 之後快速放大",d:"差距隨時間持續擴大"}],true,"差距在 3 小時就出現了");
figureSlide("12","觀看數分布：Shorts 與長影片行為不同","觀看數為 log 尺度，兩者形狀迥異","fig02_view_cdf_by_type.png",
  [{h:"Shorts 整體右移",d:"中位觀看數較高"},{h:"曲線形狀不同",d:"不能混用同一模型評估"}],false,"兩種成長行為截然不同");

// ====================================================================
// SLIDE 13 — divider 03
// ====================================================================
divider("03","資料前處理","清理　·　標籤設計　·　特徵工程　·　留言情緒　·　資料切分","13");

// ====================================================================
// SLIDE 14 — 6-step pipeline (charcoal)
// ====================================================================
s = slide(CHAR); header(s,"前處理 Pipeline：六個步驟","從原始時序到可訓練的特徵與序列",true);
const P14=[["01","時序清理"],["02","標籤生成"],["03","特徵工程","Tabular"],["04","留言情緒","特徵"],["05","序列建構","LSTM"],["06","資料切分"]];
const bw=2.78, gp=(18.2-6*bw)/5;
P14.forEach((p,i)=>{
  const x=0.9+i*(bw+gp);
  rrect(s,x,4.0,bw,3.4,CARD,{r:0.1,shadow:true});
  badge(s,x+bw/2-0.62,4.45,1.24,p[0],BLUE,CREAM);
  s.addText(p[1],{x:x+0.1,y:5.85,w:bw-0.2,h:0.7,fontSize:23,bold:true,color:CREAM,fontFace:FZH,align:"center",valign:"middle",margin:0});
  if(p[2]) s.addText(p[2],{x:x+0.1,y:6.5,w:bw-0.2,h:0.5,fontSize:18,color:BLUE,fontFace:FMONO,align:"center",margin:0});
  if(i<5) arrow(s,x+bw+gp*0.1,5.7,gp*0.8,0,BLUE);
});
notes(s,"14");

// ====================================================================
// SLIDE 15 — label design (cream, logic + code)
// ====================================================================
s = slide(CREAM); header(s,"標籤設計：爆紅是相對的，不是絕對的","以頻道規模為基準，動態決定爆紅門檻",false);
rrect(s,0.9,2.4,8.6,6.2,WHITE,{r:0.1,shadow:true});
s.addText("設計邏輯",{x:1.3,y:2.7,w:7,h:0.6,fontSize:24,bold:true,color:BLUE,fontFace:FZH,margin:0});
rrect(s,1.3,3.55,7.8,1.9,CREAM,{r:0.08});
s.addText([{text:"100 萬訂閱",options:{bold:true}},{text:" 的頻道\n",options:{breakLine:true}},{text:"10 萬觀看 ",options:{bold:true,fontSize:26,color:RED}},{text:"不算爆紅",options:{}}],
  {x:1.6,y:3.65,w:7.2,h:1.7,fontSize:22,color:CHAR,fontFace:FZH,valign:"middle",lineSpacingMultiple:1.2,margin:0});
rrect(s,1.3,5.65,7.8,1.9,CREAM,{r:0.08});
s.addText([{text:"500 訂閱",options:{bold:true}},{text:" 的小頻道\n",options:{breakLine:true}},{text:"10,000 觀看 ",options:{bold:true,fontSize:26,color:GREEN}},{text:"非常驚人",options:{}}],
  {x:1.6,y:5.75,w:7.2,h:1.7,fontSize:22,color:CHAR,fontFace:FZH,valign:"middle",lineSpacingMultiple:1.2,margin:0});
rrect(s,9.9,2.4,9.2,6.2,PANEL,{r:0.1,shadow:true});
s.addText("門檻公式",{x:10.3,y:2.7,w:7,h:0.6,fontSize:20,color:MUT_D,fontFace:FZH,margin:0});
s.addText([
  {text:"effective_sub = max(訂閱數, 1000)",options:{breakLine:true}},
  {text:" ",options:{breakLine:true,fontSize:12}},
  {text:"threshold = max(",options:{breakLine:true}},
  {text:"    10000 (Shorts) / 2000 (長影片),",options:{breakLine:true}},
  {text:"    2 × effective_sub",options:{breakLine:true}},
  {text:")",options:{breakLine:true}},
  {text:" ",options:{breakLine:true,fontSize:14}},
  {text:"is_viral = views_48h ≥ threshold",options:{bold:true,color:GREEN}},
],{x:10.3,y:3.4,w:8.4,h:5,fontSize:23,color:CREAM,fontFace:FMONO,valign:"top",lineSpacingMultiple:1.45,margin:0});
notes(s,"15");

// ====================================================================
// SLIDE 16 — viral rate figure
// ====================================================================
figureSlide("16","病毒率：12.6%，Shorts 略高於長影片","241 支爆紅 ／ 1,916 支總樣本","fig03_viral_rate_by_type.png",
  [{h:"整體病毒率 12.6%",d:"資料明顯不平衡"},{h:"Shorts 略高",d:"13.8% vs 長影片 11.9%"}],false,"類別不平衡需特別處理");

// ====================================================================
// SLIDE 17 — 5-group feature ladder (charcoal)
// ====================================================================
s = slide(CHAR); header(s,"特徵工程：五個群組，逐步疊加","量化每一類資訊帶來的邊際貢獻",true);
const G17=[
  ["A","6","靜態：訂閱數、影片長度、發布時段、類別…"],
  ["B","20","+ 早期流量：views_3h、成長率、互動率…"],
  ["C1","23","+ 留言二元情緒（RoBERTa positive score）"],
  ["C2","25","+ Valence-Arousal（regex 代理指標）"],
  ["C3","28","+ C1 + C2 全部特徵"],
];
let ly=2.45; const lh=1.5;
G17.forEach((g,i)=>{
  const ind=i*0.7, x=0.9+ind, w=15.2;
  rrect(s,x,ly,w,lh-0.18,CARD,{r:0.08,shadow:true});
  s.addShape(pres.shapes.RECTANGLE,{x,y:ly,w:1.55,h:lh-0.18,fill:{color:BLUE}});
  s.addText(g[0],{x,y:ly,w:1.55,h:lh-0.18,fontSize:34,bold:true,color:CREAM,fontFace:FBLK,align:"center",valign:"middle",margin:0});
  s.addText([{text:g[1],options:{bold:true,fontSize:34,color:CREAM}},{text:" 個特徵",options:{fontSize:20,color:MUT_D}}],
    {x:x+1.85,y:ly,w:3.6,h:lh-0.18,fontFace:FZH,valign:"middle",margin:0});
  s.addText(g[2],{x:x+5.6,y:ly,w:w-5.8,h:lh-0.18,fontSize:21,color:CREAM,fontFace:FZH,valign:"middle",margin:0});
  ly+=lh;
});
notes(s,"17");

// ====================================================================
// SLIDE 18 — RoBERTa C1 (cream, flow + doughnut)
// ====================================================================
s = slide(CREAM); header(s,"留言情緒 C1：RoBERTa 二元情感分類","以中文情感模型推論每則留言的正向程度",false);
rrect(s,0.9,2.4,10.4,8.0,WHITE,{r:0.1,shadow:true});
rrect(s,1.3,2.75,9.6,0.95,PANEL,{r:0.08});
s.addText("uer/roberta-base-finetuned-jd-binary-chinese",{x:1.3,y:2.75,w:9.6,h:0.95,fontSize:20,color:CREAM,fontFace:FMONO,align:"center",valign:"middle",margin:0});
s.addText([
  {text:"取 0–3h 留言快照",options:{breakLine:true,bold:true}},
  {text:"↓",options:{breakLine:true,color:BLUE,fontSize:24}},
  {text:"每則留言推論 positive 分數",options:{breakLine:true,bold:true}},
  {text:"↓",options:{breakLine:true,color:BLUE,fontSize:24}},
  {text:"影片層級彙整三個特徵：",options:{breakLine:true,bold:true}},
  {text:"comment_sentiment_score（平均正向）",options:{bullet:{code:"25AA"},breakLine:true,fontSize:20}},
  {text:"top_comment_like_ratio（高讚正向比）",options:{bullet:{code:"25AA"},breakLine:true,fontSize:20}},
  {text:"comment_count_3h（留言數）",options:{bullet:{code:"25AA"},fontSize:20}},
],{x:1.4,y:3.95,w:9.4,h:6.2,fontSize:22,color:CHAR,fontFace:FZH,valign:"top",lineSpacingMultiple:1.25,margin:0});
rrect(s,11.7,2.4,7.4,8.0,CHAR,{r:0.1,shadow:true});
s.addText("資料覆蓋率",{x:12.1,y:2.7,w:6,h:0.6,fontSize:22,bold:true,color:BLUE,fontFace:FZH,margin:0});
s.addChart(pres.charts.DOUGHNUT,[{name:"cov",labels:["有留言情緒","其餘填 0"],values:[34,66]}],
  {x:11.9,y:3.4,w:7.0,h:5.0,chartColors:[BLUE,CARDB],showLegend:true,legendPos:"b",legendColor:CREAM,legendFontSize:18,
   dataLabelColor:CREAM,dataLabelFontSize:18,showValue:false,holeSize:58});
s.addText([{text:"642 ",options:{bold:true,fontSize:40,color:CREAM,fontFace:FBLK}},{text:"支影片（34%）",options:{color:MUT_D,fontSize:22}}],
  {x:12.1,y:8.6,w:6.6,h:1.4,fontFace:FZH,align:"center",valign:"middle",margin:0});
notes(s,"18");

// ====================================================================
// SLIDE 19 — Valence-Arousal C2 (cream, two cards)
// ====================================================================
s = slide(CREAM); header(s,"留言情緒 C2：Valence-Arousal 不需要模型","用 regex 代理喚醒度，免額外模型即可量化情緒強度",false);
rrect(s,0.9,2.4,8.9,5.7,WHITE,{r:0.1,shadow:true});
s.addShape(pres.shapes.RECTANGLE,{x:0.9,y:2.4,w:0.14,h:5.7,fill:{color:BLUE}});
s.addText("Valence　情感極性",{x:1.35,y:2.75,w:8,h:0.7,fontSize:25,bold:true,color:BLUE,fontFace:FZH,margin:0});
s.addText("直接沿用 C1 的 positive score",{x:1.35,y:3.55,w:8,h:0.7,fontSize:22,color:CHAR,fontFace:FZH,margin:0});
s.addText([{text:"新增特徵\n",options:{bold:true,breakLine:true,color:"6E746C",fontSize:18}},
  {text:"comment_valence_mean\ncomment_arousal_mean",options:{}}],
  {x:1.35,y:4.6,w:8,h:3.2,fontSize:22,color:CHAR,fontFace:FMONO,valign:"top",lineSpacingMultiple:1.45,margin:0});
rrect(s,10.2,2.4,8.9,5.7,WHITE,{r:0.1,shadow:true});
s.addShape(pres.shapes.RECTANGLE,{x:10.2,y:2.4,w:0.14,h:5.7,fill:{color:RED}});
s.addText("Arousal　喚醒度（regex 代理）",{x:10.65,y:2.75,w:8.2,h:0.7,fontSize:25,bold:true,color:RED,fontFace:FZH,margin:0});
s.addText([
  {text:"驚嘆號密度　comment_exclamation_ratio",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:12}},
  {text:"emoji 密度　comment_emoji_ratio",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:12}},
  {text:"強烈詞彙比例　comment_intense_ratio",options:{bullet:{code:"25AA"}}},
],{x:10.65,y:3.7,w:8.2,h:4.0,fontSize:21,color:CHAR,fontFace:FZH,valign:"top",margin:0});
rrect(s,0.9,8.4,18.2,2.0,CHAR,{r:0.1,shadow:true});
s.addText([{text:"高 Arousal = 觀眾情緒激動 → 更可能分享　",options:{bold:true,color:CREAM}},{text:"｜　優點：免額外模型、速度快、覆蓋率同 C1",options:{color:MUT_D}}],
  {x:1.3,y:8.4,w:17.4,h:2.0,fontSize:23,fontFace:FZH,align:"center",valign:"middle",margin:0});
notes(s,"19");

// ====================================================================
// SLIDE 20 — naive split problem (charcoal)
// ====================================================================
s = slide(CHAR); header(s,"直接時序切分：測試集幾乎全是 Shorts","Shorts 是後期補爬，時序上集中在近期",true);
tag(s,0.9,2.2,"問題",RED,CREAM);
const ty20=4.4;
rrect(s,0.9,ty20,10.0,2.0,CARD,{r:0.08});
s.addText([{text:"Train（早期）\n",options:{bold:true,fontSize:24,color:CREAM,breakLine:true}},{text:"幾乎全是長影片",options:{color:MUT_D,fontSize:22}}],
  {x:0.9,y:ty20,w:10.0,h:2.0,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.1,margin:0});
rrect(s,11.5,ty20,7.6,2.0,BLUE,{r:0.08});
s.addText([{text:"Test（近期）\n",options:{bold:true,fontSize:24,color:CREAM,breakLine:true}},{text:"幾乎全是 Shorts",options:{color:CREAM,fontSize:22}}],
  {x:11.5,y:ty20,w:7.6,h:2.0,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.1,margin:0});
s.addText("時間軸  →",{x:0.9,y:6.6,w:18.2,h:0.6,fontSize:18,italic:true,color:MUT_D,fontFace:FZH,align:"right",margin:0});
rrect(s,3.0,7.6,14.0,2.6,PANEL,{r:0.1,shadow:true});
s.addText([
  {text:"✗  ",options:{bold:true,fontSize:40,color:RED}},
  {text:"在長影片上訓練，在 Shorts 上評估\n",options:{bold:true,color:CREAM,breakLine:true}},
  {text:"結果：毫無意義",options:{bold:true,fontSize:30,color:RED}},
],{x:3.4,y:7.6,w:13.2,h:2.6,fontSize:30,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.25,margin:0});
notes(s,"20");

// ====================================================================
// SLIDE 21 — grouped split solution (cream, fig01)
// ====================================================================
s = slide(CREAM); header(s,"解法：Shorts 和長影片各自分組切分","先分組再各自按時序切，維持每個 split 的類型均衡",false);
tag(s,0.9,2.1,"解法",BLUE,CREAM);
s.addText([
  {text:"做法\n",options:{bold:true,breakLine:true,color:BLUE,fontSize:24}},
  {text:"Shorts 按 publish_time 排序 → 70/15/15",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:8}},
  {text:"Long  按 publish_time 排序 → 70/15/15",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:8}},
  {text:"兩者合併",options:{bullet:{code:"25AA"},bold:true}},
],{x:0.95,y:3.0,w:8.4,h:3.5,fontSize:23,color:CHAR,fontFace:FZH,valign:"top",lineSpacingMultiple:1.2,margin:0});
s.addText([
  {text:"結果\n",options:{bold:true,breakLine:true,color:BLUE,fontSize:24}},
  {text:"每個 split 的 Shorts 比例維持 ~34%",options:{breakLine:true}},
],{x:0.95,y:6.6,w:8.4,h:1.4,fontSize:23,color:CHAR,fontFace:FZH,valign:"top",lineSpacingMultiple:1.2,margin:0});
[["Train","1,133"],["Valid","380"],["Test","403"]].forEach((t,i)=>{
  stat(s,0.95+i*2.85,8.1,2.6,2.0,t[1],t[0],{numSize:34,labelSize:18,dark:true});
});
fitImage(s,"fig01_data_split_balance.png",{x:10.0,y:2.3,w:9.1,h:8.3});
notes(s,"21");

// ====================================================================
// SLIDE 22 — divider 04
// ====================================================================
divider("04","模型設計","Logistic　·　LightGBM　·　LSTM　·　Stacking","22");

// ====================================================================
// SLIDE 23 — four models (charcoal, 2x2 cards w/ icon)
// ====================================================================
s = slide(CHAR); header(s,"四種模型各自的角色","從可解釋基準線，到序列模型與融合",true);
const M23=[
  ["Σ","Logistic Regression","可解釋基準線，吃 Tabular 特徵","群組 A / B / C1"],
  ["GBM","LightGBM","主力模型，跑完所有 Ablation 群組","群組 A / B / C1 / C2 / C3"],
  ["∿","LSTM","純序列模型，不使用靜態特徵","輸入 T×3 時序序列（0–3h）"],
  ["⧉","Stacking","融合 LightGBM + LSTM 的 meta-learner","輸入 兩模型 OOF 機率"],
];
const mcx=[0.9,9.95], mcy=[2.45,6.55], mcw=9.15, mch=3.8;
M23.forEach((m,i)=>{
  const x=mcx[i%2], y=mcy[Math.floor(i/2)];
  rrect(s,x,y,mcw,mch,CARD,{r:0.1,shadow:true});
  rrect(s,x+0.5,y+0.55,1.5,1.5,BLUE,{r:0.12});
  s.addText(m[0],{x:x+0.5,y:y+0.55,w:1.5,h:1.5,fontSize:m[0].length>1?22:40,bold:true,color:CREAM,fontFace:m[0].length>1?FBLK:FZH,align:"center",valign:"middle",margin:0});
  s.addText(m[1],{x:x+2.3,y:y+0.6,w:mcw-2.6,h:0.8,fontSize:27,bold:true,color:CREAM,fontFace:FZH,valign:"middle",margin:0});
  s.addText(m[2],{x:x+2.3,y:y+1.45,w:mcw-2.6,h:0.9,fontSize:20,color:MUT_D,fontFace:FZH,valign:"top",lineSpacingMultiple:1.1,margin:0});
  s.addText(m[3],{x:x+0.5,y:y+2.7,w:mcw-1.0,h:0.7,fontSize:20,bold:true,color:BLUE,fontFace:FZH,valign:"middle",margin:0});
});
notes(s,"23");

// ====================================================================
// SLIDE 24 — LightGBM 5-Fold OOF (cream, flow + uses)
// ====================================================================
s = slide(CREAM); header(s,"LightGBM：5-Fold OOF 同時服務 Ablation 與 Stacking","一次 out-of-fold 設計，兼顧公平比較與防洩漏融合",false);
rrect(s,0.9,2.6,4.7,2.5,CHAR,{r:0.1,shadow:true});
s.addText([{text:"5-Fold\n",options:{breakLine:true,fontSize:30,bold:true,color:CREAM}},{text:"Out-of-Fold (OOF)",options:{fontSize:20,color:BLUE}}],
  {x:0.9,y:2.6,w:4.7,h:2.5,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.1,margin:0});
arrow(s,5.75,3.2,1.2,0,CHAR); arrow(s,5.75,4.5,1.2,0,CHAR);
rrect(s,7.2,2.3,11.9,2.4,WHITE,{r:0.1,shadow:true}); s.addShape(pres.shapes.RECTANGLE,{x:7.2,y:2.3,w:0.14,h:2.4,fill:{color:BLUE}});
s.addText([{text:"用途一　Ablation Study\n",options:{bold:true,fontSize:24,color:BLUE,breakLine:true}},{text:"每個群組（A/B/C1/C2/C3）獨立訓練，比較 test F1 / AUC",options:{fontSize:21,color:CHAR}}],
  {x:7.6,y:2.3,w:11.1,h:2.4,fontFace:FZH,valign:"middle",lineSpacingMultiple:1.2,margin:0});
rrect(s,7.2,4.95,11.9,2.4,WHITE,{r:0.1,shadow:true}); s.addShape(pres.shapes.RECTANGLE,{x:7.2,y:4.95,w:0.14,h:2.4,fill:{color:BLUE}});
s.addText([{text:"用途二　Stacking 的輸入\n",options:{bold:true,fontSize:24,color:BLUE,breakLine:true}},{text:"OOF 預測機率 P₁ 輸入 meta-learner（模型從未在 in-sample 預測過自己）",options:{fontSize:21,color:CHAR}}],
  {x:7.6,y:4.95,w:11.1,h:2.4,fontFace:FZH,valign:"middle",lineSpacingMultiple:1.2,margin:0});
rrect(s,0.9,7.8,18.2,1.5,PANEL,{r:0.1});
s.addText([{text:"超參數　",options:{bold:true,color:BLUE}},{text:"num_leaves = 63    learning_rate = 0.05    rounds = 500",options:{color:CREAM}}],
  {x:0.9,y:7.8,w:18.2,h:1.5,fontSize:24,fontFace:FMONO,align:"center",valign:"middle",margin:0});
notes(s,"24");

// ====================================================================
// SLIDE 25 — LSTM (charcoal, matrix + arch)
// ====================================================================
s = slide(CHAR); header(s,"LSTM：T×3 序列，捕捉早期動態","以正規化的逐時序列，學習成長的形狀",true);
rrect(s,0.9,2.5,8.4,8.0,PANEL,{r:0.1,shadow:true});
const mx0=2.0,my0=4.0,cwd=1.6,chd=0.78;
["view","like","comment"].forEach((c,i)=>s.addText(c,{x:mx0+i*cwd,y:my0-0.65,w:cwd,h:0.5,fontSize:17,bold:true,color:BLUE,fontFace:FMONO,align:"center",margin:0}));
for(let r=0;r<5;r++)for(let c=0;c<3;c++){
  s.addShape(pres.shapes.RECTANGLE,{x:mx0+c*cwd,y:my0+r*chd,w:cwd-0.08,h:chd-0.08,fill:{color:CARD},line:{color:CARDB,width:1}});
}
s.addText("t = 0",{x:mx0-1.35,y:my0,w:1.2,h:chd,fontSize:15,color:MUT_D,fontFace:FMONO,align:"right",valign:"middle",margin:0});
s.addText("⋮",{x:mx0,y:my0+5*chd-0.1,w:3*cwd,h:0.5,fontSize:24,color:MUT_D,align:"center",margin:0});
s.addText("T × 3 序列",{x:mx0-0.5,y:my0+5*chd+0.35,w:3*cwd+1,h:0.6,fontSize:22,bold:true,color:CREAM,fontFace:FZH,align:"center",margin:0});
s.addText([
  {text:"輸入格式\n",options:{bold:true,breakLine:true,color:BLUE,fontSize:24}},
  {text:"T ≈ 18–36 步（每 5–10 分鐘一筆）",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:8}},
  {text:"3 維度：view / like / comment count",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:8}},
  {text:"每維除以該影片窗口內最大值",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:24}},
  {text:"架構\n",options:{bold:true,breakLine:true,color:BLUE,fontSize:24}},
  {text:"hidden = 64, layers = 2, dropout = 0.3",options:{bullet:{code:"25AA"},breakLine:true,paraSpaceAfter:8}},
  {text:"損失：BCELoss + pos_weight（處理不平衡）",options:{bullet:{code:"25AA"}}},
],{x:10.0,y:2.9,w:9.1,h:7.5,fontSize:22,color:CREAM,fontFace:FZH,valign:"top",lineSpacingMultiple:1.2,margin:0});
notes(s,"25");

// ====================================================================
// SLIDE 26 — Stacking (cream, flow)
// ====================================================================
s = slide(CREAM); header(s,"Stacking：OOF 防洩漏設計","兩個基模型的 OOF 機率，交給 meta-learner 融合",false);
function pill(x,y,w,h,main,subt,fill,tc){ rrect(s,x,y,w,h,fill,{r:0.1,shadow:true});
  s.addText([{text:main,options:{bold:true,fontSize:22}},...(subt?[{text:"\n"+subt,options:{fontSize:17,color:tc==CREAM?MUT_D:"6E746C"}}]:[])],
    {x:x+0.1,y,w:w-0.2,h,color:tc,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.0,margin:0}); }
pill(0.9,2.7,5.0,1.4,"LightGBM (5-Fold OOF)","",WHITE,CHAR);
pill(0.9,4.6,5.0,1.4,"LSTM (5-Fold OOF)","",WHITE,CHAR);
s.addText("P₁",{x:6.1,y:2.7,w:1.0,h:1.4,fontSize:30,bold:true,color:BLUE,fontFace:FBLK,align:"center",valign:"middle",margin:0});
s.addText("P₂",{x:6.1,y:4.6,w:1.0,h:1.4,fontSize:30,bold:true,color:BLUE,fontFace:FBLK,align:"center",valign:"middle",margin:0});
arrow(s,7.2,3.4,1.5,0.5,CHAR); arrow(s,7.2,5.3,1.5,-0.5,CHAR);
pill(8.9,3.05,4.6,1.4,"[P₁, P₂] → Logistic","meta-learner",CHAR,CREAM);
arrow(s,13.6,3.75,1.3,0,CHAR);
pill(15.0,3.05,4.1,1.4,"最終機率 P","",BLUE,CREAM);
rrect(s,0.9,7.3,18.2,3.0,WHITE,{r:0.1,shadow:true,line:{color:BLUE,width:2,dashType:"dash"}});
s.addText("防洩漏保證",{x:1.3,y:7.55,w:8,h:0.6,fontSize:24,bold:true,color:BLUE,fontFace:FZH,margin:0});
s.addText([
  {text:"P₁ / P₂ 皆為 OOF 預測，meta 從未見過 in-sample",options:{bullet:{code:"2713"},breakLine:true,paraSpaceAfter:10}},
  {text:"meta-learner 只在 OOF 上訓練，不碰 test set",options:{bullet:{code:"2713"},breakLine:true,paraSpaceAfter:10}},
  {text:"Scaler 僅 fit on train",options:{bullet:{code:"2713"}}},
],{x:1.4,y:8.2,w:17.4,h:2.0,fontSize:22,color:CHAR,fontFace:FZH,valign:"top",margin:0});
notes(s,"26");

// ====================================================================
// SLIDE 27 — divider 05
// ====================================================================
divider("05","分類實驗結果","Ablation　·　SHAP　·　留言情緒　·　完整成績","27");

// ====================================================================
// SLIDE 28 — ablation figure (wide)
// ====================================================================
figureSlide("28","Ablation：五個群組的 F1 與 AUC","逐步加入特徵群組，觀察分數變化","fig13_ablation_classification.png",
  [{h:"A → B 跳躍最大",d:"加入早期流量帶來最大增益"},{h:"C 系列微幅提升",d:"留言情緒為錦上添花"}],true);

// ====================================================================
// SLIDE 29 — big jump 0.327 -> 0.731 (charcoal)
// ====================================================================
s = slide(CHAR); header(s,"加入早期流量：F1 從 0.327 跳到 0.731","靜態特徵不夠，影片本身的早期反應才是關鍵",true);
s.addText("0.327",{x:0.9,y:3.4,w:6.6,h:2.6,fontSize:120,bold:true,color:MUT_D,fontFace:FBLK,align:"center",valign:"middle",margin:0});
s.addText("僅靜態特徵 (A)",{x:0.9,y:6.0,w:6.6,h:0.6,fontSize:20,color:MUT_D,fontFace:FZH,align:"center",margin:0});
s.addShape("rightArrow",{x:7.9,y:4.0,w:2.2,h:1.4,fill:{color:BLUE}});
s.addText("0.731",{x:10.5,y:3.4,w:6.6,h:2.6,fontSize:120,bold:true,color:CREAM,fontFace:FBLK,align:"center",valign:"middle",margin:0});
s.addText("加入早期流量 (B)",{x:10.5,y:6.0,w:6.6,h:0.6,fontSize:20,color:BLUE,fontFace:FZH,align:"center",margin:0});
stat(s,17.4,3.6,2.1,2.6,"+124%","F1 增幅",{dark:true,numSize:30,labelSize:16,accent:RED});
rrect(s,0.9,7.4,18.2,2.9,CARD,{r:0.1,shadow:true});
s.addText([{text:"AUC　",options:{color:MUT_D}},{text:"0.733 → 0.937",options:{bold:true,color:CREAM}},{text:"（+27.8%）",options:{color:BLUE,bold:true}}],
  {x:1.3,y:7.7,w:17.4,h:1.0,fontSize:30,fontFace:FZH,align:"center",valign:"middle",margin:0});
s.addText("結論：靜態特徵不夠，早期行為才是關鍵信號",{x:1.3,y:8.8,w:17.4,h:1.2,fontSize:28,bold:true,color:CREAM,fontFace:FZH,align:"center",valign:"middle",margin:0});
notes(s,"29");

// ====================================================================
// SLIDE 30 — views3h figure (wide)
// ====================================================================
figureSlide("30","為什麼早期流量有效：Viral 在 3h 就已領先","以 3 小時觀看數中位數對比兩群影片","fig07_views3h_vs_viral.png",
  [{h:"Viral 中位 = 1,312",d:""},{h:"Non-viral 中位 = 184",d:"兩者相差 7 倍，在第 3 小時就出現"}],false);

// ====================================================================
// SLIDE 31 — SHAP figure (tall, side panel)
// ====================================================================
figureSlide("31","SHAP 特徵重要性：哪些特徵最關鍵？","以 SHAP 解讀 LightGBM 的特徵貢獻","fig06_shap_importance.png",
  [{h:"訂閱數壓倒性領先",d:"log_subscriber_count 高居第一"},{h:"早期流量緊隨其後",d:"views_3h、view_delta 為 #2、#3"}],true,"第一名與第二名之間有一條鴻溝");

// ====================================================================
// SLIDE 32 — top-3 SHAP features (charcoal)
// ====================================================================
s = slide(CHAR); header(s,"log_subscriber_count SHAP = 第二名的 2.7 倍","受眾規模是基礎，但早期流量同樣不可或缺",true);
const T32=[["#1","log_subscriber_count","2.109",46,CREAM],["#2","views_3h","0.770",34,CREAM],["#3","view_delta_1h_3h","0.683",26,MUT_D]];
let ty32=2.35;
T32.forEach((t,i)=>{
  const big = i==0;
  rrect(s,0.9,ty32,18.2,big?1.7:1.2,big?BLUE:CARD,{r:0.08,shadow:true});
  s.addText(t[0],{x:1.2,y:ty32,w:1.6,h:big?1.7:1.2,fontSize:big?46:32,bold:true,color:CREAM,fontFace:FBLK,valign:"middle",margin:0});
  s.addText(t[1],{x:3.0,y:ty32,w:11,h:big?1.7:1.2,fontSize:big?40:28,bold:true,color:CREAM,fontFace:FMONO,valign:"middle",margin:0});
  s.addText([{text:"SHAP ",options:{fontSize:18,color:big?CREAM:MUT_D}},{text:t[2],options:{bold:true,fontSize:big?40:28,color:CREAM,fontFace:FBLK}}],
    {x:13.5,y:ty32,w:5.4,h:big?1.7:1.2,fontFace:FZH,align:"right",valign:"middle",margin:0});
  ty32 += (big?1.7:1.2)+0.18;
});
rrect(s,0.9,7.35,18.2,3.0,PANEL,{r:0.1,shadow:true});
s.addText([
  {text:"第一名是第二名的 2.7 倍\n",options:{bold:true,fontSize:28,color:BLUE,breakLine:true}},
  {text:"受眾規模是爆紅的基礎；但 #2、#3 都是早期流量——\n",options:{breakLine:true}},
  {text:"光有受眾不夠，影片本身也必須在 3 小時內引起反應。",options:{}},
],{x:1.3,y:7.55,w:17.4,h:2.6,fontSize:26,color:CREAM,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.25,margin:0});
notes(s,"32");

// table cell helper
function cell(t,o={}){ return {text:t,options:Object.assign({fontFace:FZH,align:"center",valign:"middle"},o)}; }

// ====================================================================
// SLIDE 33 — comment sentiment benefit table (cream)
// ====================================================================
s = slide(CREAM); header(s,"留言情緒的效益：C2 Precision 提升最顯著","C2 只用 regex，效果卻比 RoBERTa 的 C1 更明顯",false);
const h33=["特徵組","F1","Precision","AUC"].map(t=>cell(t,{bold:true,color:CREAM,fill:{color:CHAR},fontSize:24}));
const r33=[["B（基準）","0.731","73.1%","0.937",0],["C1","0.752","+4.4%","0.943",0],["C2 ★","0.763","+9.1% → 82%","0.934",1],["C3","0.740","+4.0%","0.939",0]];
const t33=[h33];
r33.forEach(r=>{const hot=r[4]==1;t33.push(r.slice(0,4).map((c,i)=>cell(c,{bold:hot||i==0,color:hot?CREAM:CHAR,fill:{color:hot?BLUE:WHITE},fontSize:hot?24:22})));});
s.addTable(t33,{x:1.5,y:2.6,w:17,colW:[4.25,4.25,4.25,4.25],rowH:1.0,border:{pt:1.5,color:CREAM},valign:"middle"});
rrect(s,1.5,8.6,17,1.7,CHAR,{r:0.1,shadow:true});
s.addText([{text:"結論　",options:{bold:true,color:BLUE}},{text:"C2（喚醒度 regex）比 C1（RoBERTa）效果更明顯，且免額外模型",options:{color:CREAM}}],
  {x:1.9,y:8.6,w:16.2,h:1.7,fontSize:24,fontFace:FZH,align:"center",valign:"middle",margin:0});
notes(s,"33");

// ====================================================================
// SLIDE 34 — valence-arousal figure (tall)
// ====================================================================
figureSlide("34","Valence-Arousal：高喚醒留言集中在 Viral 影片","留言情緒在二維空間的分布","fig17_comment_valence_arousal.png",
  [{h:"右上象限 Viral 偏高",d:"高 Valence + 高 Arousal 區"},{h:"情緒越強烈越易爆紅",d:"觀眾越興奮，分享動機越強"}],false,"高喚醒留言指向爆紅");

// ====================================================================
// SLIDE 35 — full classification table (charcoal) + stat row
// ====================================================================
s = slide(CHAR); header(s,"完整分類成績：所有模型對比","LightGBM 全面領先，LSTM 單獨使用接近隨機",true);
[["0.763","F1 最高 · LightGBM C2"],["0.943","AUC 最高 · LightGBM C1"],["0.832","PR-AUC 最高 · LightGBM C3"]].forEach((v,i)=>{
  stat(s,0.9+i*6.15,2.15,5.8,1.5,v[0],v[1],{dark:true,numSize:40,labelSize:17});
});
const h35=["模型","群組","F1","AUC","PR-AUC"].map(t=>cell(t,{bold:true,color:CREAM,fill:{color:PANEL},fontSize:20}));
const d35=[["Logistic","A","0.283","0.643","0.209",0],["Logistic","B","0.520","0.905","0.649",0],["Logistic","C1","0.528","0.907","0.650",0],
["LightGBM","A","0.327","0.733","0.280",0],["LightGBM","B","0.731","0.937","0.800",0],["LightGBM ★","C1","0.752","0.943","0.818",1],
["LightGBM ★","C2","0.763","0.934","0.809",1],["LightGBM","C3","0.740","0.939","0.832",0],["LSTM","B","0.257","0.590","0.146",2],["Stacking","B","0.674","0.919","0.783",0]];
const t35=[h35];
d35.forEach(r=>{const f=r[5];const fill=f==1?BLUE:(f==2?"3A3D39":CARD);const col=f==2?MUT_D:CREAM;
  t35.push(r.slice(0,5).map(c=>cell(c,{bold:f==1,color:col,fill:{color:fill},fontSize:18})));});
s.addTable(t35,{x:3.0,y:4.0,w:14,colW:[3.6,2.0,2.8,2.8,2.8],rowH:0.59,border:{pt:1,color:PANEL},valign:"middle"});
notes(s,"35");

// ====================================================================
// SLIDES 36,37,38 — figures
// ====================================================================
figureSlide("36","ROC 曲線：LightGBM 顯著領先","各模型在不同閾值下的真陽性／偽陽性權衡","fig09_roc_curves.png",
  [{h:"LightGBM 緊貼左上角",d:"AUC = 0.943"},{h:"LSTM 最低",d:"AUC = 0.590，接近隨機"}],false);
figureSlide("37","PR 曲線：不平衡資料下的真實評估","病毒率僅 12.6%，PR 曲線比 ROC 更誠實","fig10_pr_curves.png",
  [{h:"Random baseline = 0.126",d:"不是 0.5"},{h:"LightGBM C3 = 0.832",d:"約為隨機的 6.6 倍"}],true);
figureSlide("38","Confusion Matrix：模型在哪裡犯錯？","在極不平衡的資料下，漏判的代價最高","fig11_confusion_matrix_lgbm.png",
  [{h:"False Negative 最關鍵",d:"漏抓的爆紅影片"},{h:"病毒率僅 12.6%",d:"漏判等於錯過真正爆紅"}],false,"FN 是最昂貴的錯誤");

// ====================================================================
// SLIDE 39 — divider 06
// ====================================================================
divider("06","迴歸實驗結果","R² = 0.853　·　預測 vs 實際　·　殘差分析","39");

// ====================================================================
// SLIDE 40 — regression results (charcoal) + stats + application
// ====================================================================
s = slide(CHAR); header(s,"迴歸成績：R² = 0.853，LightGBM 優於 LSTM","已知前 48 小時，可預估未來 24 小時的成長量",true);
[["0.853","R² · LightGBM C1"],["0.835","MAE · log 尺度"],["1.162","RMSE · LightGBM C1"]].forEach((v,i)=>{
  stat(s,0.9+i*6.15,2.15,5.8,1.5,v[0],v[1],{dark:true,numSize:40,labelSize:17});
});
const h40=["模型","群組","R²","MAE","RMSE"].map(t=>cell(t,{bold:true,color:CREAM,fill:{color:PANEL},fontSize:22}));
const d40=[["LightGBM","B","0.851","0.841","1.172",0],["LightGBM ★","C1","0.853","0.835","1.162",1],["LSTM","B","0.705","1.137","1.610",0]];
const t40=[h40];
d40.forEach(r=>{const hot=r[5]==1;t40.push(r.slice(0,5).map(c=>cell(c,{bold:hot,color:CREAM,fill:{color:hot?BLUE:CARD},fontSize:22})));});
s.addTable(t40,{x:3.0,y:4.0,w:14,colW:[3.6,2.0,2.8,2.8,2.8],rowH:0.8,border:{pt:1,color:PANEL},valign:"middle"});
s.addText("MAE 0.835（log 尺度）≈ 實際觀看數誤差約 ×2.3 倍",{x:0.9,y:7.0,w:18.2,h:0.6,fontSize:22,italic:true,color:MUT_D,fontFace:FZH,align:"center",margin:0});
rrect(s,2.5,7.9,15,2.1,BLUE,{r:0.1,shadow:true});
s.addText([{text:"應用　",options:{bold:true,fontSize:26,color:CREAM}},{text:"創作者在發布 48 小時後，可預估接下來 24h 的成長量",options:{color:CREAM}}],
  {x:2.9,y:7.9,w:14.2,h:2.1,fontSize:25,fontFace:FZH,align:"center",valign:"middle",lineSpacingMultiple:1.2,margin:0});
notes(s,"40");

// ====================================================================
// SLIDES 41,42,43 — regression figures
// ====================================================================
figureSlide("41","預測 vs 實際：點越貼近對角線代表越準","Shorts 與長影片皆有良好預測","fig14_reg_pred_vs_actual.png",
  [{h:"點貼近對角線",d:"預測值接近真實值"},{h:"兩類型皆準",d:"Shorts、Long 都對齊良好"}],false);
figureSlide("42","殘差分析：大誤差集中在突然爆發的影片","殘差主體集中在 0，但有明顯長尾","fig15_reg_residuals.png",
  [{h:"主體集中在 0",d:"大多數預測準確"},{h:"長尾 = 突然爆發",d:"難以預測 viral cascade"}],true);
figureSlide("43","迴歸 Ablation：特徵群組與模型比較","早期流量是主力，情緒特徵僅錦上添花","fig16_ablation_regression.png",
  [{h:"LightGBM ≫ LSTM",d:"R² 0.853 vs 0.705"},{h:"B → C1 微幅",d:"留言情緒對迴歸效益有限"}],false);

// ====================================================================
// SLIDE 44 — divider 07
// ====================================================================
divider("07","結論","五個帶得走的洞見","44");

// ====================================================================
// SLIDE 45 — five takeaways (blue, checkmark rows)
// ====================================================================
s = slide(BLUE); header(s,"我們學到什麼：五個帶走的結論","",true);
const TK=[
  ["3 小時資料已足以預測爆紅","AUC = 0.943"],
  ["受眾規模是爆紅的基礎","log_subscriber SHAP = 2.109"],
  ["早期觀看速度是最強即時信號","views_3h SHAP = 0.770"],
  ["留言喚醒度有效（即使只有 regex）","Precision +12%"],
  ["評估設計本身很重要","分組切分才能公平"],
];
let ty45=1.95;
TK.forEach((t,i)=>{
  rrect(s,0.9,ty45,18.2,1.28,CHAR,{r:0.08,shadow:true});
  s.addShape(pres.shapes.OVAL,{x:1.25,y:ty45+0.3,w:0.68,h:0.68,fill:{color:BLUE}});
  s.addText("✓",{x:1.25,y:ty45+0.3,w:0.68,h:0.68,fontSize:24,bold:true,color:CREAM,fontFace:FZH,align:"center",valign:"middle",margin:0});
  s.addText(t[0],{x:2.3,y:ty45,w:11.0,h:1.28,fontSize:27,bold:true,color:CREAM,fontFace:FZH,valign:"middle",margin:0});
  s.addText(t[1],{x:13.3,y:ty45,w:5.5,h:1.28,fontSize:22,bold:true,color:BLUE,fontFace:FMONO,align:"right",valign:"middle",margin:0});
  ty45 += 1.42;
});
notes(s,"45");

// ====================================================================
// SLIDE 46 — closing quote (charcoal)
// ====================================================================
s = slide(CHAR);
const cv2=[[14.0,2.2],[15.3,2.8],[16.4,3.6],[17.3,5.0],[18.0,6.8],[18.6,8.6]];
for(let i=0;i<cv2.length-1;i++) s.addShape(pres.shapes.LINE,{x:cv2[i][0],y:cv2[i][1],w:cv2[i+1][0]-cv2[i][0],h:cv2[i+1][1]-cv2[i][1],line:{color:BLUE,width:2.5,transparency:55}});
s.addText([
  {text:"發布後 ",options:{}},{text:"3 小時",options:{color:BLUE}},{text:"，\n",options:{breakLine:true}},
  {text:"不只是等待的時間——\n",options:{breakLine:true}},
  {text:"它是",options:{}},{text:"預測的窗口",options:{color:BLUE}},{text:"。",options:{}},
],{x:1.2,y:3.2,w:14,h:4.8,fontSize:60,bold:true,color:CREAM,fontFace:FZH,align:"left",valign:"middle",lineSpacingMultiple:1.3,margin:0});
s.addText("謝謝聆聽　·　資料探勘導論 2026 期末專題",{x:1.2,y:9.4,w:14,h:0.6,fontSize:20,color:MUT_D,fontFace:FZH,margin:0});
notes(s,"46");

// ====================================================================
pres.writeFile({ fileName: "/sessions/jolly-youthful-hypatia/mnt/outputs/YouTube_爆紅預測_簡報.pptx" }).then(f=>console.log("WROTE",f));
