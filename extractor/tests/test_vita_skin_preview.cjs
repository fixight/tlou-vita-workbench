const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const V=require('../vita_skin_preview.js');
for(const value of [0,-0,1,-1,.5,65504,2**-24,2**-14,1.0009765625])assert.equal(V.unhalf(V.half(value)),value);
assert.equal(V.unhalf(V.half(1+2**-11)),1);assert.equal(V.unhalf(V.half(1+3*2**-11)),1+2*2**-10);
assert.throws(()=>V.half(Infinity));assert.throws(()=>V.half(70000));
const synthetic={count:1,basePositions:new Float32Array([.12345,.56789,-.0101]),baseNormals:new Float32Array([0,1,0]),baseUvs:new Float32Array([.25,.75]),joints:new Uint16Array([300,200,100,0]),weights:new Float32Array([.4,.3,.2,.1])};
const sample=V.prepare(synthetic);assert.equal(sample.packed.byteLength,16);assert.equal(sample.full.joints[0],300);
assert(Math.abs(sample.two.weights[0]-4/7)<1e-6);assert.equal(sample.affected,1);assert(Math.abs(sample.discarded-.3)<1e-6);
assert.equal(new DataView(sample.packed).getUint8(15),0);
const reports=[];
for(const character of ['sarah','young-joel']){
 const binary=fs.readFileSync(path.join(__dirname,'../extracted_models',character,character+'.glb'));
 const jsonSize=binary.readUInt32LE(12),gltf=JSON.parse(binary.subarray(20,20+jsonSize).toString());
 const binStart=20+jsonSize+8;
 function attr(index){const a=gltf.accessors[index],v=gltf.bufferViews[a.bufferView],size={SCALAR:1,VEC2:2,VEC3:3,VEC4:4}[a.type],out=[];
  const bytes={5126:4,5123:2,5121:1}[a.componentType],start=binStart+(v.byteOffset||0)+(a.byteOffset||0),stride=v.byteStride||bytes*size;
  for(let i=0;i<a.count;i++)for(let k=0;k<size;k++){const p=start+i*stride+k*bytes;out.push(a.componentType===5126?binary.readFloatLE(p):a.componentType===5123?binary.readUInt16LE(p):binary.readUInt8(p));}return out;}
 let count=0,affected=0,loss=0,maxPositionError=0,maxPalette=0;
 for(const mesh of gltf.meshes)for(const p of mesh.primitives){if(p.attributes.JOINTS_0===undefined)continue;
  const prim={count:gltf.accessors[p.attributes.POSITION].count,basePositions:new Float32Array(attr(p.attributes.POSITION)),
   baseNormals:p.attributes.NORMAL===undefined?null:new Float32Array(attr(p.attributes.NORMAL)),baseUvs:p.attributes.TEXCOORD_0===undefined?null:new Float32Array(attr(p.attributes.TEXCOORD_0)),
   joints:new Uint16Array(attr(p.attributes.JOINTS_0)),weights:new Float32Array(attr(p.attributes.WEIGHTS_0))};
  const original=prim.weights.slice(),v=V.prepare(prim);assert.equal(v.packed.byteLength,prim.count*16);assert.deepEqual(prim.weights,original);
  for(let i=0;i<prim.count;i++){
   assert(Math.abs(v.full.weights[i*4]+v.full.weights[i*4+1]-1)<1e-6);
   assert.equal(v.full.joints[i*4],v.two.joints[i*4]);assert.equal(v.full.joints[i*4+1],v.two.joints[i*4+1]);
   for(let a=0;a<3;a++){const error=Math.abs(v.full.basePositions[i*3+a]-prim.basePositions[i*3+a]);maxPositionError=Math.max(maxPositionError,error);assert(error<=.0005002);}
  }
  count+=prim.count;affected+=v.affected;loss+=v.discarded;maxPalette=Math.max(maxPalette,v.palette.length);
 }
 reports.push({character,vertices:count,packedBytes:count*16,moreThanTwoInfluencesPercent:100*affected/count,averageDiscardedWeightPercent:100*loss/count,maxPositionErrorMetres:maxPositionError,maxPalette});
}
fs.writeFileSync(path.join(__dirname,'../tests_temp_out/vita_skin_quality_report.json'),JSON.stringify(reports,null,2));
console.log('PASS: half float ties, 16-byte ABI, high source joint IDs, normalized weights, untouched originals, actual Sarah/Joel meshes');console.log(reports);
