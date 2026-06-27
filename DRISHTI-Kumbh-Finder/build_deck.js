const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE";            // 13.3 x 7.5
p.author = "DRISHTI";
p.title = "DRISHTI — Kumbh Mela Missing Person Finder";

// palette
const INK = "161123", INK2 = "241A4A", SAFFRON = "FF6A00", GOLD = "F5A623",
      WHITE = "FFFFFF", TINT = "FFF4EC", TXT = "1A2027", MUTED = "6B7682",
      GREEN = "2EA043", LINE = "E3E0EC";
const SERIF = "Cambria", SANS = "Calibri";
const W = 13.33, H = 7.5;
const sh = () => ({ type: "outer", color: "000000", blur: 9, offset: 3, angle: 90, opacity: 0.12 });

function pageNum(s, n){ s.addText(`${n}`, {x:W-0.8,y:H-0.5,w:0.5,h:0.3,fontSize:10,color:MUTED,align:"right",fontFace:SANS}); }
function kicker(s, t, color){ s.addText(t.toUpperCase(), {x:0.7,y:0.55,w:11,h:0.35,fontSize:13,bold:true,color:color||SAFFRON,charSpacing:3,fontFace:SANS}); }
function title(s, t, color){ s.addText(t, {x:0.7,y:0.9,w:12,h:0.9,fontSize:32,bold:true,color:color||TXT,fontFace:SERIF}); }

// stat card
function statCard(s, x, y, w, val, label, sub){
  s.addShape(p.shapes.ROUNDED_RECTANGLE,{x,y,w,h:1.85,fill:{color:WHITE},line:{color:LINE,width:1},rectRadius:0.08,shadow:sh()});
  s.addText(val,{x:x+0.1,y:y+0.18,w:w-0.2,h:0.85,fontSize:40,bold:true,color:SAFFRON,align:"center",fontFace:SERIF,margin:0});
  s.addText(label,{x:x+0.1,y:y+1.05,w:w-0.2,h:0.35,fontSize:13,bold:true,color:TXT,align:"center",fontFace:SANS,margin:0});
  if(sub) s.addText(sub,{x:x+0.1,y:y+1.4,w:w-0.2,h:0.35,fontSize:10,color:MUTED,align:"center",fontFace:SANS,margin:0});
}

/* ---------------- 1. TITLE ---------------- */
let s = p.addSlide(); s.background = {color: INK};
s.addShape(p.shapes.OVAL,{x:9.3,y:-2,w:7,h:7,fill:{color:INK2}});
s.addShape(p.shapes.OVAL,{x:11.2,y:2.8,w:4.5,h:4.5,fill:{color:SAFFRON,transparency:78}});
s.addShape(p.shapes.OVAL,{x:0.75,y:1.05,w:1.1,h:1.1,fill:{color:SAFFRON},shadow:sh()});
s.addShape(p.shapes.OVAL,{x:0.95,y:1.25,w:0.7,h:0.7,fill:{color:WHITE}});
s.addShape(p.shapes.OVAL,{x:1.13,y:1.43,w:0.34,h:0.34,fill:{color:INK}});
s.addText("DRISHTI", {x:0.7,y:2.25,w:11,h:1.1,fontSize:62,bold:true,color:WHITE,fontFace:SERIF,charSpacing:2});
s.addText("Finding missing people in real time at the Kumbh Mela",
  {x:0.72,y:3.45,w:11,h:0.6,fontSize:22,color:GOLD,fontFace:SANS});
s.addText("A real-time face-matching prototype for the Nashik–Trimbakeshwar Simhastha Kumbh Mela 2027 — designed for a crowd of ~12 crore pilgrims.",
  {x:0.72,y:4.2,w:9.8,h:0.9,fontSize:15,color:"C9C3D9",fontFace:SANS,lineSpacingMultiple:1.2});
s.addText([{text:"Detect",options:{color:SAFFRON,bold:true}},{text:"  →  ",options:{color:MUTED}},
  {text:"Embed",options:{color:SAFFRON,bold:true}},{text:"  →  ",options:{color:MUTED}},
  {text:"Match",options:{color:SAFFRON,bold:true}},{text:"  →  ",options:{color:MUTED}},
  {text:"Reunite",options:{color:GREEN,bold:true}}],
  {x:0.72,y:5.4,w:11,h:0.5,fontSize:18,fontFace:SANS});
s.addText("Hackathon prototype · 2026", {x:0.72,y:6.6,w:6,h:0.4,fontSize:12,color:MUTED,fontFace:SANS});

/* ---------------- 2. PROBLEM ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"The problem"); title(s,"Getting lost in the world's largest gathering");
s.addText([
 {text:"The Kumbh Mela is the biggest peaceful human gathering on Earth — and separation from family is one of its most common, frightening experiences.",options:{breakLine:true,paraSpaceAfter:10}},
 {text:"The traditional fix — a loudspeaker and a lost-and-found (Bhula-Bhatka) tent — is slow, passive, and useless for someone who is disoriented, wandering, or can't ask for help.",options:{breakLine:true,paraSpaceAfter:10}},
 {text:"The elderly, children, and non-local-language speakers are most at risk, and every hour of separation is acute distress.",options:{}}
],{x:0.7,y:2.0,w:6.0,h:3.6,fontSize:16,color:TXT,fontFace:SANS,lineSpacingMultiple:1.25,valign:"top"});

s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:7.1,y:2.0,w:5.5,h:4.4,fill:{color:TINT},line:{color:SAFFRON,width:1.2},rectRadius:0.1,shadow:sh()});
s.addText("Why it's hard",{x:7.4,y:2.25,w:5,h:0.5,fontSize:18,bold:true,color:SAFFRON,fontFace:SERIF});
s.addText([
 {text:"Tens of thousands reported missing across a single mela",options:{bullet:true,breakLine:true,paraSpaceAfter:8}},
 {text:"Up to 2.5 crore people on a single peak day",options:{bullet:true,breakLine:true,paraSpaceAfter:8}},
 {text:"A wandering person rarely stays near a booth",options:{bullet:true,breakLine:true,paraSpaceAfter:8}},
 {text:"Manual CCTV review can't keep up with the crowd",options:{bullet:true,breakLine:true,paraSpaceAfter:8}},
 {text:"Children change appearance fast & have few photos",options:{bullet:true}}
],{x:7.45,y:2.95,w:4.9,h:3.3,fontSize:14.5,color:TXT,fontFace:SANS,lineSpacingMultiple:1.1,valign:"top"});
pageNum(s,2);

/* ---------------- 3. SCALE ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"The scale — Nashik 2027 ground truth");
title(s,"We design for the actual deployment");
statCard(s,0.7,2.0,2.85,"12 cr","Pilgrims expected","across the full mela");
statCard(s,3.75,2.0,2.85,"2.5 cr","Peak-day footfall","≈ 25 million in one day");
statCard(s,6.8,2.0,2.85,"4,011","AI CCTV cameras","+ 18 surveillance drones");
statCard(s,9.85,2.0,2.75,"₹300 cr","Surveillance budget","state \"Kumbh AI Stack\"");
s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:0.7,y:4.3,w:11.9,h:2.3,fill:{color:INK},rectRadius:0.1,shadow:sh()});
s.addText("Where the cameras are — and where people get lost",{x:1.05,y:4.5,w:11,h:0.5,fontSize:17,bold:true,color:GOLD,fontFace:SERIF});
s.addText([
 {text:"Ramkund ghats (densest zone) · surrounding ghats · Sadhugram akhada camps · Trimbakeshwar temple (~30 km away) · Nashik Road railway station · CBS bus stand · Ramkund Marg corridor.",options:{breakLine:true,paraSpaceAfter:8}},
 {text:"Two sites, 30 km apart, one search space — a person lost at Ramkund may resurface at Trimbakeshwar. That's why DRISHTI uses ONE central vector index across all 4,011 cameras, not per-camera search.",options:{color:"C9C3D9"}}
],{x:1.05,y:5.05,w:11.3,h:1.4,fontSize:13.5,color:WHITE,fontFace:SANS,lineSpacingMultiple:1.15,valign:"top"});
pageNum(s,3);

/* ---------------- 4. PRECEDENT ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"It already works");
title(s,"Prayagraj 2025 proved the concept");
s.addText("At the Maha Kumbh 2025, authorities used AI facial recognition to locate lost people for the first time — when someone was reported missing, the system scanned the camera network and traced their route through CCTV. India's police already run a national face-recognition system that has matched thousands of missing-child cases.",
 {x:0.7,y:1.95,w:11.9,h:1.3,fontSize:16,color:TXT,fontFace:SANS,lineSpacingMultiple:1.25,valign:"top"});
statCard(s,0.7,3.5,2.85,"2,750+","AI CCTV cameras","Prayagraj 2025");
statCard(s,3.75,3.5,2.85,"100","Face-recog cameras","at major stations");
statCard(s,6.8,3.5,2.85,"10","Lost-&-found booths","tech-equipped");
statCard(s,9.85,3.5,2.75,"1000s","Missing children","matched by AFRS");
s.addText("DRISHTI takes this proven idea and purpose-builds it for Nashik 2027: family-facing, privacy-bounded, and tuned to the site's geography.",
 {x:0.7,y:5.7,w:11.9,h:0.8,fontSize:14,italic:true,color:SAFFRON,fontFace:SANS});
pageNum(s,4);

/* ---------------- 5. SOLUTION ---------------- */
s = p.addSlide(); s.background={color:INK};
kicker(s,"The solution",GOLD); title(s,"DRISHTI: an active search layer",WHITE);
s.addText("Family gives a photo → DRISHTI searches the live camera network → reports where that face appears, in near-real time.",
 {x:0.7,y:1.85,w:11.9,h:0.7,fontSize:16,color:"C9C3D9",fontFace:SANS});
const steps=[["1","Register","Family submits a photo + consent at a booth or in the app. DRISHTI stores only a face-print."],
 ["2","Search","Every face on every camera is matched against the watch-list in milliseconds."],
 ["3","Locate","A match pins the camera, location & time and reconstructs the person's path."],
 ["4","Reunite","Family + nearest booth are alerted; an operator confirms before dispatch."]];
steps.forEach((st,i)=>{
  const x=0.7+i*3.0;
  s.addShape(p.shapes.ROUNDED_RECTANGLE,{x,y:2.9,w:2.8,h:3.4,fill:{color:INK2},rectRadius:0.1,shadow:sh()});
  s.addShape(p.shapes.OVAL,{x:x+1.1,y:3.15,w:0.6,h:0.6,fill:{color:SAFFRON}});
  s.addText(st[0],{x:x+1.1,y:3.15,w:0.6,h:0.6,fontSize:24,bold:true,color:INK,align:"center",valign:"middle",fontFace:SERIF,margin:0});
  s.addText(st[1],{x:x+0.15,y:3.95,w:2.5,h:0.5,fontSize:19,bold:true,color:WHITE,align:"center",fontFace:SERIF});
  s.addText(st[2],{x:x+0.25,y:4.55,w:2.3,h:1.6,fontSize:13,color:"C9C3D9",align:"center",fontFace:SANS,lineSpacingMultiple:1.15,valign:"top"});
});
s.addText("Opt-in reunification — not blanket surveillance.",{x:0.7,y:6.65,w:11.9,h:0.4,fontSize:14,italic:true,bold:true,color:GOLD,align:"center",fontFace:SANS});
pageNum(s,5);

/* ---------------- 6. HOW IT WORKS (pipeline svg) ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"How it works"); title(s,"Detect → Embed → Match → Alert");
s.addImage({path:"architecture_pipeline.svg",x:0.55,y:1.85,w:12.2,h:5.2});
pageNum(s,6);

/* ---------------- 7. ARCHITECTURE (system svg) ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"Architecture"); title(s,"Edge · Core · Consumers");
s.addImage({path:"architecture_system.svg",x:0.6,y:1.75,w:12.1,h:5.4});
pageNum(s,7);

/* ---------------- 8. TECH STACK ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"The engine room"); title(s,"Proven open-source, built to scale");
const rows=[
 ["Detect faces","SCRFD / RetinaFace","strong even in dense, occluded crowds"],
 ["Embed (face-print)","ArcFace · InsightFace","512-D vector, robust to light & pose"],
 ["Match at scale","FAISS / Milvus","top-k over millions of vectors in <50 ms"],
 ["Track across cameras","ByteTrack","reconstructs the person's route"],
 ["Run 4,011 streams","NVIDIA DeepStream + TensorRT","edge GPU; sends vectors, not raw video"]];
let yy=2.05;
rows.forEach((r,i)=>{
  s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:0.7,y:yy,w:11.9,h:0.86,fill:{color:i%2?TINT:WHITE},line:{color:LINE,width:1},rectRadius:0.06});
  s.addText(r[0],{x:0.95,y:yy,w:3.1,h:0.86,fontSize:15,bold:true,color:TXT,valign:"middle",fontFace:SANS,margin:0});
  s.addText(r[1],{x:4.2,y:yy,w:3.7,h:0.86,fontSize:15,bold:true,color:SAFFRON,valign:"middle",fontFace:SANS,margin:0});
  s.addText(r[2],{x:8.0,y:yy,w:4.4,h:0.86,fontSize:13,color:MUTED,valign:"middle",fontFace:SANS,margin:0});
  yy+=0.97;
});
s.addText("≈100 edge GPUs feed one central vector index — comfortably within the ₹300 cr envelope.",
 {x:0.7,y:yy+0.05,w:11.9,h:0.4,fontSize:13,italic:true,color:TXT,fontFace:SANS});
pageNum(s,8);

/* ---------------- 9. PROTOTYPE ---------------- */
s = p.addSlide(); s.background={color:INK};
kicker(s,"The prototype",GOLD); title(s,"A working demo you can run today",WHITE);
s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:0.7,y:2.0,w:5.85,h:4.5,fill:{color:INK2},rectRadius:0.1,shadow:sh()});
s.addText("index.html — zero install",{x:1.0,y:2.25,w:5.3,h:0.5,fontSize:19,bold:true,color:SAFFRON,fontFace:SERIF});
s.addText([
 {text:"Real face recognition in the browser (TensorFlow.js)",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"Register a missing person from a photo",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"12-tile simulated Kumbh camera wall",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"Live detection, matching, boxes & alerts",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"Match log + command dashboard",options:{bullet:true}}
],{x:1.05,y:3.0,w:5.3,h:3.3,fontSize:14.5,color:"E8E4F2",fontFace:SANS,valign:"top"});

s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:6.75,y:2.0,w:5.85,h:4.5,fill:{color:INK2},rectRadius:0.1,shadow:sh()});
s.addText("backend_reference.py — production stack",{x:7.05,y:2.25,w:5.3,h:0.5,fontSize:19,bold:true,color:SAFFRON,fontFace:SERIF});
s.addText([
 {text:"Same logic, real models: SCRFD + ArcFace + FAISS",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"FastAPI: /enroll · /search · /watchlist · /stats",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"Interactive Swagger docs",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"GPU-ready: swap to onnxruntime-gpu + faiss-gpu",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"The blueprint for the real deployment",options:{bullet:true}}
],{x:7.1,y:3.0,w:5.3,h:3.3,fontSize:14.5,color:"E8E4F2",fontFace:SANS,valign:"top"});
s.addText("Demo flow: register a sample face → drop a crowd photo into a feed → watch DRISHTI find them.",
 {x:0.7,y:6.7,w:11.9,h:0.4,fontSize:13,italic:true,color:GOLD,align:"center",fontFace:SANS});
pageNum(s,9);

/* ---------------- 10. PRIVACY ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"Privacy & ethics"); title(s,"Built for the DPDP Act 2023");
const pr=[["Consent & purpose limit","Matches ONLY against photos a family explicitly submitted to find a specific person."],
 ["Data minimisation","Non-matching faces are never stored. Raw video stays at the edge — only vectors travel."],
 ["Automatic deletion","All watch-list embeddings & logs purged when the mela ends."],
 ["Human oversight","Every match is operator-confirmed; every access is logged & auditable."]];
pr.forEach((c,i)=>{
  const x=0.7+(i%2)*6.05, y=2.0+Math.floor(i/2)*2.25;
  s.addShape(p.shapes.ROUNDED_RECTANGLE,{x,y,w:5.85,h:2.0,fill:{color:TINT},line:{color:LINE,width:1},rectRadius:0.1,shadow:sh()});
  s.addShape(p.shapes.OVAL,{x:x+0.3,y:y+0.32,w:0.55,h:0.55,fill:{color:SAFFRON}});
  s.addText(`${i+1}`,{x:x+0.3,y:y+0.32,w:0.55,h:0.55,fontSize:22,bold:true,color:WHITE,align:"center",valign:"middle",fontFace:SERIF,margin:0});
  s.addText(c[0],{x:x+1.05,y:y+0.3,w:4.6,h:0.6,fontSize:17,bold:true,color:TXT,fontFace:SERIF,valign:"middle"});
  s.addText(c[1],{x:x+0.35,y:y+1.0,w:5.2,h:0.9,fontSize:13.5,color:TXT,fontFace:SANS,lineSpacingMultiple:1.1,valign:"top"});
});
s.addText("Civil-society groups warn against weak guardrails. We treat those concerns as design requirements — governance is a first-class layer, not an afterthought.",
 {x:0.7,y:6.55,w:11.9,h:0.6,fontSize:13,italic:true,color:MUTED,fontFace:SANS});
pageNum(s,10);

/* ---------------- 11. IMPACT + ROADMAP ---------------- */
s = p.addSlide(); s.background={color:WHITE};
kicker(s,"Impact & roadmap"); title(s,"Measured in reunions, not faces scanned");
s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:0.7,y:2.0,w:5.85,h:4.4,fill:{color:TINT},line:{color:SAFFRON,width:1.2},rectRadius:0.1,shadow:sh()});
s.addText("Success metrics",{x:1.0,y:2.2,w:5,h:0.5,fontSize:18,bold:true,color:SAFFRON,fontFace:SERIF});
s.addText([
 {text:"Median time-to-reunion (minutes, not hours)",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"% of reported missing persons located",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"Children located — highest priority",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"False-positive rate at operating threshold",options:{bullet:true,breakLine:true,paraSpaceAfter:9}},
 {text:"Accuracy parity across demographics",options:{bullet:true}}
],{x:1.05,y:2.85,w:5.2,h:3.4,fontSize:14.5,color:TXT,fontFace:SANS,valign:"top"});

s.addShape(p.shapes.ROUNDED_RECTANGLE,{x:6.75,y:2.0,w:5.85,h:4.4,fill:{color:INK},rectRadius:0.1,shadow:sh()});
s.addText("Roadmap",{x:7.05,y:2.2,w:5,h:0.5,fontSize:18,bold:true,color:GOLD,fontFace:SERIF});
s.addText([
 {text:"Prototype — demo + reference backend ✓",options:{bullet:true,breakLine:true,paraSpaceAfter:10,color:GREEN,bold:true}},
 {text:"Pilot — Ramkund ghat cluster, one booth",options:{bullet:true,breakLine:true,paraSpaceAfter:10}},
 {text:"Scale-out — all 4,011 cameras + family app",options:{bullet:true,breakLine:true,paraSpaceAfter:10}},
 {text:"Harden — bias audit, DPDP layer, peak load",options:{bullet:true,breakLine:true,paraSpaceAfter:10}},
 {text:"Reuse — future melas + stampede warning",options:{bullet:true}}
],{x:7.1,y:2.85,w:5.3,h:3.4,fontSize:14.5,color:"E8E4F2",fontFace:SANS,valign:"top"});
pageNum(s,11);

/* ---------------- 12. CLOSING ---------------- */
s = p.addSlide(); s.background={color:INK};
s.addShape(p.shapes.OVAL,{x:-2,y:3.5,w:7,h:7,fill:{color:INK2}});
s.addShape(p.shapes.OVAL,{x:10,y:-2.5,w:5.5,h:5.5,fill:{color:SAFFRON,transparency:80}});
s.addShape(p.shapes.OVAL,{x:0.75,y:1.6,w:1.0,h:1.0,fill:{color:SAFFRON},shadow:sh()});
s.addShape(p.shapes.OVAL,{x:0.93,y:1.78,w:0.64,h:0.64,fill:{color:WHITE}});
s.addShape(p.shapes.OVAL,{x:1.1,y:1.95,w:0.3,h:0.3,fill:{color:INK}});
s.addText("Bring families back together —",{x:0.7,y:2.9,w:12,h:0.9,fontSize:40,bold:true,color:WHITE,fontFace:SERIF});
s.addText("in real time, at any scale.",{x:0.7,y:3.8,w:12,h:0.9,fontSize:40,bold:true,color:SAFFRON,fontFace:SERIF});
s.addText("DRISHTI · Kumbh Mela Missing Person Finder",{x:0.72,y:5.0,w:11,h:0.5,fontSize:17,color:GOLD,fontFace:SANS});
s.addText("Prototype + research report + architecture + this deck — all in one package.",
 {x:0.72,y:5.6,w:11,h:0.5,fontSize:13,color:"C9C3D9",fontFace:SANS});

p.writeFile({fileName:"DRISHTI_Pitch_Deck.pptx"}).then(f=>console.log("WROTE",f));
