import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildTimeline, locateTime} from '../cinematic_timeline.mjs';

const timeline=buildTimeline([{duration:2},{duration:3},{duration:4}]);

test('Crossing a cut preserves excess time without pausing or losing frames',()=>{
    assert.deepEqual(locateTime(timeline,2.125),{index:1,local:.125,absolute:2.125});
    assert.deepEqual(locateTime(timeline,5),{index:2,local:0,absolute:5});
});
test('Backward scrubbing and final frame resolve deterministically',()=>{
    assert.deepEqual(locateTime(timeline,1),{index:0,local:1,absolute:1});
    assert.deepEqual(locateTime(timeline,100),{index:2,local:4,absolute:9});
    assert.deepEqual(locateTime(timeline,-1),{index:0,local:0,absolute:0});
});
test('Large advances can cross multiple fragments',()=>{
    assert.deepEqual(locateTime(timeline,7.5),{index:2,local:2.5,absolute:7.5});
});
test('Invalid timeline values fail explicitly',()=>{
    assert.throws(()=>buildTimeline([]));
    assert.throws(()=>buildTimeline([{duration:NaN}]));
    assert.throws(()=>buildTimeline([{duration:0}]));
    assert.throws(()=>locateTime(timeline,Infinity));
});
test('Exported scene resolves every native fragment boundary',()=>{
    const scene=JSON.parse(readFileSync(new URL('../output_study_cinematic/scene.json',import.meta.url)));
    const actual=buildTimeline(scene.stages);
    for(const entry of actual.entries){
        const point=locateTime(actual,entry.start);
        assert.equal(point.index,entry.index);
        assert.equal(point.local,0);
    }
    assert.equal(locateTime(actual,actual.duration).index,scene.stages.length-1);
});
