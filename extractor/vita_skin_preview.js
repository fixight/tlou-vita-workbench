/* Actual 16-byte round-trip for visual quality comparison, not a Vita FPS model. */
(function(root){
'use strict';
const tmp=new DataView(new ArrayBuffer(4));
function half(x){
 tmp.setFloat32(0,x,true);const bits=tmp.getUint32(0,true),sign=(bits>>>16)&0x8000;
 const e=((bits>>>23)&255)-127,m=bits&0x7fffff;
 if(!Number.isFinite(x))throw Error('Non-finite UV');
 if(e>15)throw Error('UV exceeds half-float range');
 if(e < -25)return sign;
 let exponent=e+15, significand=m|0x800000;
 let shift=e < -14 ? -e-1 : 13;
 let rounded=Math.floor(significand/2**shift),remainder=significand%(2**shift),mid=2**(shift-1);
 if(remainder>mid||(remainder===mid&&(rounded&1)))rounded++;
 if(e < -14)return sign|rounded;
 if(rounded>=2048){exponent++;rounded=1024;}
 if(exponent>=31)throw Error('UV exceeds half-float range');
 return sign|(exponent<<10)|(rounded&1023);
}
function unhalf(h){const s=h&32768?-1:1,e=(h>>>10)&31,m=h&1023;return s*(e===0?m*2**-24:e===31?(m?NaN:Infinity):(1+m/1024)*2**(e-15));}
function oct(n){
 let [x,y,z]=n,den=Math.abs(x)+Math.abs(y)+Math.abs(z);if(!den)return [0,0];x/=den;y/=den;z/=den;
 if(z<0){const old=x;x=(1-Math.abs(y))*(old>=0?1:-1);y=(1-Math.abs(old))*(y>=0?1:-1);}
 return [Math.round(x*127),Math.round(y*127)];
}
function unoct(a,b){let x=a/127,y=b/127,z=1-Math.abs(x)-Math.abs(y);if(z<0){const old=x;x=(1-Math.abs(y))*(old>=0?1:-1);y=(1-Math.abs(old))*(y>=0?1:-1);}const len=Math.hypot(x,y,z)||1;return [x/len,y/len,z/len];}
function prepare(prim,step=.001){
 if(!(step>0&&Number.isFinite(step)))throw Error('Invalid position step');
 const count=prim.count,twoJ=new Uint16Array(count*4),twoW=new Float32Array(count*4);
 const palette=[],lookup=new Map();let affected=0,discarded=0,maxDiscarded=0;
 for(let i=0;i<count;i++){
  const combined=new Map();let total=0;
  for(let k=0;k<4;k++){const w=prim.weights[i*4+k],j=prim.joints[i*4+k];
   if(!Number.isFinite(w)||w<0||!Number.isInteger(j)||j<0||j>65535)throw Error('Invalid skin weights/joints');
   if(w>0){combined.set(j,(combined.get(j)||0)+w);total+=w;}}
  const influences=[...combined.entries()].sort((a,b)=>b[1]-a[1]||a[0]-b[0]);
  if(!influences.length)influences.push([prim.joints[i*4],1]);
  const first=influences[0],second=influences[1]||[first[0],0],kept=first[1]+second[1];
  const loss=total>0?Math.max(0,1-kept/total):0;
  if(influences.length>2)affected++;discarded+=loss;maxDiscarded=Math.max(maxDiscarded,loss);
  twoJ[i*4]=first[0];twoJ[i*4+1]=second[0];twoW[i*4]=first[1]/kept;twoW[i*4+1]=second[1]/kept;
  for(const j of [first[0],second[0]])if(!lookup.has(j)){lookup.set(j,palette.length);palette.push(j);}
 }
 if(palette.length>256)throw Error('Более 256 используемых костей в детали; нужен раздельный формат/батч');
 const lower=[Infinity,Infinity,Infinity],upper=[-Infinity,-Infinity,-Infinity];
 for(let i=0;i<count;i++)for(let a=0;a<3;a++){const p=prim.basePositions[i*3+a];if(!Number.isFinite(p))throw Error('Non-finite position');lower[a]=Math.min(lower[a],p);upper[a]=Math.max(upper[a],p);}
 const origin=lower.map((v,a)=>Math.round((v+upper[a])/(2*step))*step);
 const packed=new ArrayBuffer(count*16),view=new DataView(packed);
 const pos=new Float32Array(count*3),norm=new Float32Array(count*3),uv=new Float32Array(count*2),joints=new Uint16Array(count*4),weights=new Float32Array(count*4);
 for(let i=0;i<count;i++){
  const o=i*16;
  for(let a=0;a<3;a++){const q=Math.round((prim.basePositions[i*3+a]-origin[a])/step);if(q<-32768||q>32767)throw Error('Position exceeds int16 range');view.setInt16(o+a*2,q,true);pos[i*3+a]=view.getInt16(o+a*2,true)*step+origin[a];}
  for(let a=0;a<2;a++){view.setUint16(o+6+a*2,half(prim.baseUvs?prim.baseUvs[i*2+a]:0),true);uv[i*2+a]=unhalf(view.getUint16(o+6+a*2,true));}
  const n=oct(prim.baseNormals?prim.baseNormals.subarray(i*3,i*3+3):[0,1,0]);view.setInt8(o+10,n[0]);view.setInt8(o+11,n[1]);norm.set(unoct(view.getInt8(o+10),view.getInt8(o+11)),i*3);
  view.setUint8(o+12,lookup.get(twoJ[i*4]));view.setUint8(o+13,lookup.get(twoJ[i*4+1]));
  view.setUint8(o+14,Math.round(twoW[i*4]*255));view.setUint8(o+15,0);
  joints[i*4]=palette[view.getUint8(o+12)];joints[i*4+1]=palette[view.getUint8(o+13)];
  weights[i*4]=view.getUint8(o+14)/255;weights[i*4+1]=1-weights[i*4];
 }
 return {packed,palette,origin,step,affected,discarded,maxDiscarded,
  two:{basePositions:prim.basePositions,baseNormals:prim.baseNormals,joints:twoJ,weights:twoW},
  full:{basePositions:pos,baseNormals:norm,baseUvs:uv,joints,weights}};
}
const api={prepare,half,unhalf,oct,unoct};root.VitaSkinPreview=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:window);
