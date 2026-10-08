import * as THREE from 'three';
import { GLTFLoader } from './cinematic_vendor/GLTFLoader.js';
import { OrbitControls } from './cinematic_vendor/OrbitControls.js';
import { buildTimeline, locateTime } from './cinematic_timeline.mjs';
import { verticalFov, sampleLens, cameraBlend } from './cinematic_lens.mjs';

const ui = Object.fromEntries(['stage','continuous','play','restart','view','seek','speed','house','cutaway','studyDoors','labels','follow','cameraMode','fold','time','status','error'].map(id=>[id,document.getElementById(id)]));
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x202831);
const camera = new THREE.PerspectiveCamera(60,innerWidth/innerHeight,.03,250);
const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth,innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.localClippingEnabled = true;
const cutPlane=new THREE.Plane(new THREE.Vector3(0,-1,0),30.05);
document.body.append(renderer.domElement);
const controls = new OrbitControls(camera,renderer.domElement);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffeadb,0x829bb0,2));
const light = new THREE.DirectionalLight(0xffffff,2);
light.position.set(5,10,4);scene.add(light);
const actors = new Map();
const loader = new GLTFLoader();
let manifest, stage, timeline, house, stageIndex=-1;
let playing=false, time=0, playbackTime=0, last=performance.now(), lastFocus;
const bedroom = new URLSearchParams(location.search).get('scene') === 'bedroom';
const base = bedroom ? './output_bedroom_cinematic/' : './output_study_cinematic/';

function nativeCamera(){return ui.cameraMode.value==='native'&&stage?.camera;}

function updateNativeCamera(){
    const track=nativeCamera();if(!track)return;
    const frame=Math.min(time*track.fps,track.samples.length-1),index=Math.floor(frame);
    const before=track.samples[index],after=track.samples[Math.min(index+1,track.samples.length-1)];
    const position=new THREE.Vector3().fromArray(before),nextPosition=new THREE.Vector3().fromArray(after);
    const rotation=new THREE.Quaternion().fromArray(before,3),nextRotation=new THREE.Quaternion().fromArray(after,3);
    // Use the authored camera cut marker; older manifests retain the jump guard.
    const jump=position.distanceTo(nextPosition)>1||rotation.angleTo(nextRotation)>Math.PI/4;
    const blend=track.lens?cameraBlend(track,index,frame-index):(jump?0:frame-index);
    camera.position.copy(position.lerp(nextPosition,blend));
    camera.quaternion.copy(rotation.slerp(nextRotation,blend));
    const lens=sampleLens(track,frame,blend);
    camera.fov=lens.axis==='horizontal'?verticalFov(lens.fov,camera.aspect):lens.fov;
    camera.userData.nativeLens=lens;
    const lensStatus=document.getElementById('lensStatus');
    if(lensStatus){
        const depth=lens.depthOfField;
        lensStatus.textContent=lens.focalLength===undefined?'':
            `${lens.focalLength.toFixed(2)} мм · FOV H ${lens.fov.toFixed(2)}° / V ${camera.fov.toFixed(2)}°`+
            (depth?` · резкая область ${depth[2].toFixed(2)}–${depth[3].toFixed(2)} м`:'');
    }
    camera.updateProjectionMatrix();
}

function cameraModeChanged(){
    controls.enabled=!nativeCamera();
    ui.follow.disabled=!!nativeCamera();
    if(nativeCamera())updateNativeCamera();else frameView();
}

function actorLabel(text){
    const canvas = document.createElement('canvas');canvas.width=256;canvas.height=64;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#17202ada';ctx.fillRect(0,0,256,64);
    ctx.fillStyle='white';ctx.font='32px system-ui';ctx.textAlign='center';ctx.fillText(text,128,44);
    const material=new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),depthTest:false});
    const sprite=new THREE.Sprite(material);sprite.scale.set(1,.25,1);sprite.renderOrder=100;
    scene.add(sprite);return sprite;
}

function sample(){
    if(!stage)return;
    for(const actor of actors.values())actor.model.visible=actor.label.visible=false;
    for(const binding of stage.actors){
        const actor=actors.get(binding.id);actor.model.visible=true;
        const frame=Math.min(time*binding.motion.fps,binding.motion.samples.length-1);
        const index=Math.floor(frame),weight=frame-index;
        const before=binding.motion.samples[index],after=binding.motion.samples[Math.min(index+1,binding.motion.samples.length-1)];
        actor.model.position.fromArray(before).lerp(new THREE.Vector3().fromArray(after),weight);
        actor.model.quaternion.fromArray(before,3).slerp(new THREE.Quaternion().fromArray(after,3),weight);
        // Absolute clock permits stable forward/backward scrubbing and pauses.
        actor.action.time=Math.min(time,Math.max(0,binding.duration-.00001));
        actor.mixer.update(0);actor.model.updateMatrixWorld(true);
        const bone=actor.model.getObjectByName('heada')||actor.model.getObjectByName('neck')||actor.model.getObjectByName('root');
        actor.label.position.copy(bone.getWorldPosition(new THREE.Vector3())).add(new THREE.Vector3(0,.32,0));
        actor.label.visible=ui.labels.checked;
    }
    const controlEvents=stage.control?.events;
    const controlEvent=controlEvents?.filter(event=>event.time<=time).at(-1);
    const controlStatus=document.getElementById('controlStatus');
    if(controlStatus&&controlEvent){
        const labels={full_cinematic:'Катсцена: управление закрыто',camera_only:'Разрешён только поворот игровой камеры',gameplay:'Игровое управление'};
        controlStatus.textContent=(labels[controlEvent.profile]||controlEvent.profile)+' · настройка порта';
    }
    ui.seek.value=playbackTime;
    ui.time.textContent=`${playbackTime.toFixed(2)} / ${playbackDuration().toFixed(2)} с`;
    const focus=stage.actors.slice(0,2).reduce((sum,b)=>sum.add(actors.get(b.id).model.getObjectByName('root').getWorldPosition(new THREE.Vector3())),new THREE.Vector3()).multiplyScalar(.5);
    if(lastFocus&&ui.follow.checked&&!nativeCamera()){
        const delta=focus.clone().sub(lastFocus);camera.position.add(delta);controls.target.add(delta);
    }
    lastFocus=focus;
    updateNativeCamera();
}

function frameView(){
    if(!stage)return;
    if(nativeCamera())return;
    const positions=stage.actors.map(b=>actors.get(b.id).model.getObjectByName('root').getWorldPosition(new THREE.Vector3()));
    // Dead Jimmy and Tommy outside the house should not pull the inspection
    // camera away from Sarah and Joel.
    const focus=positions.slice(0,2).reduce((a,b)=>a.add(b),new THREE.Vector3()).multiplyScalar(1/Math.min(2,positions.length));
    focus.y+=.6;controls.target.copy(focus);
    camera.position.copy(focus).add(new THREE.Vector3(3.2,1.8,4.5));
    controls.update();
}

function playbackDuration(){
    return ui.continuous.checked ? timeline.duration : stage.duration;
}

function activateStage(index){
    stageIndex=index;
    stage=manifest.stages[index];
    lastFocus=null;
    for(const actor of actors.values())actor.mixer.stopAllAction();
    for(const binding of stage.actors){
        const actor=actors.get(binding.id);
        const clip=actor.clips.find(c=>c.name===binding.clip);
        if(!clip)throw new Error('Отсутствует клип '+binding.clip);
        actor.action=actor.mixer.clipAction(clip);
        actor.action.reset();
        actor.action.setLoop(THREE.LoopOnce,1);
        actor.action.clampWhenFinished=true;
        actor.action.play();
    }
    ui.stage.value=index;
    controls.enabled=!nativeCamera();
    ui.follow.disabled=!!nativeCamera();
    ui.status.textContent=`${index+1}/${manifest.stages.length} · ${stage.label}`;
}

function seekPlayback(value){
    if(!timeline)return;
    const located=ui.continuous.checked
        ? locateTime(timeline,value)
        : {index:stageIndex,local:Math.max(0,Math.min(value,stage.duration))};
    playbackTime=ui.continuous.checked ? located.absolute : located.local;
    time=located.local;
    if(stageIndex!==located.index)activateStage(located.index);
    ui.seek.max=playbackDuration();
    sample();
}

function selectStage(index){
    if(!timeline)return;
    if(!ui.continuous.checked)activateStage(index);
    seekPlayback(ui.continuous.checked ? timeline.entries[index].start : 0);
    if(!nativeCamera())frameView();
}

async function start(){
    const response=await fetch(base+'scene.json');if(!response.ok)throw new Error('Не найден экспорт сцены: '+base+'scene.json');
    manifest=await response.json();
    if(manifest.title){
        document.title=manifest.title;
        document.getElementById('sceneTitle').textContent=manifest.title;
        document.getElementById('sceneDescription').textContent=manifest.description+' '+manifest.limitations.join('. ')+'.';
    }
    if(manifest.cutaway_height!==undefined)cutPlane.constant=manifest.cutaway_height;
    if(bedroom){ui.studyDoors.closest('label').hidden=true;document.getElementById('doorExplanation').hidden=true;}
    timeline=buildTimeline(manifest.stages);
    await Promise.all(Object.entries(manifest.actors).map(async([id,definition])=>{
        const gltf=await loader.loadAsync(base+definition.glb);
        // Bind-pose bounds do not cover native root offsets (e.g. Sarah's
        // backup clip has a ~17 m authoring offset cancelled by apReference).
        // This small inspection scene must not cull a correctly skinned actor.
        gltf.scene.traverse(object=>{if(object.isSkinnedMesh)object.frustumCulled=false;});
        scene.add(gltf.scene);
        actors.set(id,{model:gltf.scene,clips:gltf.animations,mixer:new THREE.AnimationMixer(gltf.scene),label:actorLabel(definition.label)});
    }));
    const gltf=await loader.loadAsync(base+manifest.house);house=gltf.scene;
    house.traverse(object=>{
        if(!object.isMesh)return;
        const convert=m=>new THREE.MeshBasicMaterial({map:m.map,color:m.color,vertexColors:!!object.geometry.attributes.color,
            transparent:m.transparent,opacity:m.opacity,alphaTest:m.alphaTest,side:m.side,clippingPlanes:ui.cutaway.checked?[cutPlane]:[]});
        object.material=Array.isArray(object.material)?object.material.map(convert):convert(object.material);
        // Their scripted open pose is not yet reconstructed. Keep the native
        // camera visible rather than presenting closed export geometry as fact.
        if(!bedroom&&object.name.startsWith('hom-hs-double-door-1_'))object.visible=ui.studyDoors.checked;
        if(manifest.hide_static_prefixes?.some(prefix=>object.name.startsWith(prefix)))object.visible=false;
    });
    scene.add(house);
    manifest.stages.forEach((s,i)=>ui.stage.add(new Option(s.label,i)));
    for(const id of ['stage','continuous','play','restart','seek'])ui[id].disabled=false;
    selectStage(0);
    window.cinematicTest={actors,manifest,selectStage,sample,setTime:seekPlayback};
}

ui.stage.onchange=()=>selectStage(Number(ui.stage.value));
ui.play.onclick=()=>{
    if(!timeline)return;
    if(!playing&&playbackTime>=playbackDuration())seekPlayback(0);
    playing=!playing;
    last=performance.now();
    ui.play.textContent=playing?'Ⅱ Пауза':'▶ Играть';
};
ui.restart.onclick=()=>seekPlayback(0);
ui.seek.oninput=()=>seekPlayback(Number(ui.seek.value));
ui.continuous.onchange=()=>{
    const value=ui.continuous.checked ? timeline.entries[stageIndex].start+time : time;
    seekPlayback(value);
};
ui.house.onchange=()=>{if(house)house.visible=ui.house.checked;};
ui.cutaway.onchange=()=>{if(house)house.traverse(o=>{if(o.isMesh)for(const m of [].concat(o.material)){m.clippingPlanes=ui.cutaway.checked?[cutPlane]:[];m.needsUpdate=true;}});};
ui.studyDoors.onchange=()=>{if(house)house.traverse(o=>{if(o.name.startsWith('hom-hs-double-door-1_'))o.visible=ui.studyDoors.checked;});};
ui.labels.onchange=sample;
ui.view.onclick=()=>{ui.cameraMode.value='free';cameraModeChanged();};
ui.cameraMode.onchange=cameraModeChanged;
ui.fold.onclick=()=>{const folded=document.getElementById('panel').classList.toggle('collapsed');ui.fold.textContent=folded?'Развернуть':'Свернуть';};
window.addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
function render(now){
    const dt=Math.min((now-last)/1000,.1);last=now;
    if(playing&&stage){
        seekPlayback(playbackTime+dt*Number(ui.speed.value));
        if(playbackTime>=playbackDuration()){playing=false;ui.play.textContent='▶ Играть';}
    }
    if(!nativeCamera())controls.update();renderer.render(scene,camera);requestAnimationFrame(render);
}
requestAnimationFrame(render);
start().catch(error=>{ui.error.textContent=String(error);ui.status.textContent='Ошибка загрузки';console.error(error);});
