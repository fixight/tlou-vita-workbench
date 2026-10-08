"""Rebuild native streaming data from the user's game files. No game code runs."""
import argparse
import json
import re
from pathlib import Path
from tlou_extractor.streaming_export import prepare_streaming, task_graphs
from tlou_extractor.streaming_package import write_package


def symbols(data, wanted, source):
    table=[]
    for value in range(256):
        h=value<<24
        for _ in range(8):h=((h<<1)^(0x04c11db7 if h&0x80000000 else 0))&0xffffffff
        table.append(h)
    found={}
    for m in re.finditer(rb'[a-zA-Z*][a-zA-Z0-9_?!+*/.:-]{2,100}(?=\x00)',data):
        h=0
        for c in m.group():h=((h<<8)&0xffffffff)^table[(h>>24)^c]
        key=f'0x{h:08x}'
        if key in wanted:found[key]={'name':m.group().decode('ascii'),'source':source,'offset':m.start()}
    return found


def build(game_main, folders, world, output, level_files=None):
    graphs=task_graphs(game_main)
    cache=Path(__file__).parent/'output/task_graphs.json'
    cache.write_text(json.dumps(graphs,indent=2),encoding='utf-8')
    # Chapter-specific file discovery is explicit; metadata parsing is generic.
    world_paths=[p for folder in folders for p in Path(folder).glob(world+'-ingame*.pak')]
    if not world_paths:raise ValueError('World gameplay PAK not found: '+world)
    paks=list(world_paths)
    # Discover gameplay companion levels through the world's direct resource refs.
    base=prepare_streaming([(str(p),p.name) for p in paks],folders=folders,game_main=game_main)
    names=set(base['levels'])
    for folder in folders:
        paks.extend(p for p in Path(folder).glob('*-ingame*.pak') if re.sub(r'-ingame\d*$', '', p.stem) in names and p not in paks)
    result=prepare_streaming([(str(p),p.name) for p in paks],folders=folders,game_main=game_main)
    wanted=set(re.findall(r'0x[0-9a-f]{8}',json.dumps(result)))
    labels={}
    for p in paks:labels.update(symbols(p.read_bytes(),wanted,p.name))
    eboot=Path(game_main).parents[2]/'eboot.bin'
    if eboot.exists():labels.update(symbols(eboot.read_bytes(),wanted,'eboot.bin'))
    for chapter,g in graphs.items():
        labels[g['id']]={'name':chapter,'source':'dc1/tasks.bin','offset':g['offset']}
        for key,n in g['nodes'].items():labels[key]={'name':n['name'],'source':'dc1/tasks.bin','offset':n['offset']}
    result['symbols']=labels
    from .selector_rules import conditions
    rules=[]
    for region in result['regions']:
        if region['type']=='streaming_region':
            rules.append({'id':region['id'],'parts':len(region['shapes']),
                'selection_paths':conditions(region['selector'],labels),'sets':region['sets'],
                'bounds':[{'min':s['bounds_min'],'max':s['bounds_max']} for s in region['shapes']]})
    result['query_contracts']={
        '0xf1360136':{'name':'task-complete?','arguments':['chapter_id','task_id'],'result':'task status complete',
                      'evidence':'dc1/nd-script-funcs.bin entry f1360136 -> task-find -> ebee8318'},
        '0x4d2bf414':{'name':'before-task?','arguments':['chapter_id','task_id'],'result':'!task-complete? && !task-active?',
                      'evidence':'dc1/script-user-funcs.bin entry 4d2bf414, code 0x7f90'},
        '0x13e68c9f':{'name':'task-active?','arguments':['chapter_id','task_id'],'result':'task status active',
                      'evidence':'dc1/nd-script-funcs.bin entry 13e68c9f -> task-find -> task-subnode-active?'},
        '0xa93d2926':{'name':'object-spawned?','arguments':['object_id']},
        '0xf307e431':{'name':'get-boolean','arguments':['property_id','object_id']}}
    result['host_state_notes']={'0x69c85a6d':'ss-hom-player-settings-1 (original PAK object name)',
        '0x4f12da44':'Boolean, default false (player-settings declaration 0x930 -> 0x95c). '
        'Set true by sarah-car on-start (label 0x1745 -> handler 0x6b0 -> action list 0xa48/0xa70 -> '
        'code 0xef0 -> set-boolean, property ID, 1, self). Escape code 0x1e00 also sets it true on '
        'ss-hom-player-settings-1. Original property spelling unresolved; API alias SetSarahCarStarted.'}
    output=Path(output)
    result=write_package(result,output,level_files)
    (output/'trigger_rules.json').write_text(json.dumps(rules,ensure_ascii=False,indent=2),encoding='utf-8')
    import shutil
    shutil.copyfile(Path(__file__).resolve().parents[2]/'tlou_extractor/NativeStreaming.h',output/'NativeStreaming.h')
    for chapter,g in graphs.items():
        if g['world']!=world:continue
        links=[]
        for edge in g['edges']:
            a=g['nodes'].get(edge['from'],{}).get('name',edge['from'])
            b=g['nodes'].get(edge['to'],{}).get('name',edge['to'])
            links.append(a+' -> '+b)
        (output/(chapter+'_task_links.txt')).write_text('\n'.join(links),encoding='utf-8')
        if chapter=='home':
            node_names=[n['name'] for n in g['nodes'].values()]
            header=['#pragma once','#include "NativeStreaming.h"','namespace TlouStreaming {',
                    'inline StoryState InitialHomeState(){','    StoryState state;']
            header.extend('    state.SetTask("home",'+json.dumps(n)+',TaskStatus::Pending);' for n in node_names)
            header.extend(['    state.SetTask("home","hom-house-daughter-room-phone",TaskStatus::Active);',
                           '    state.spawned[0x69c85a6du]=true; // hom-const script object instantiated',
                           '    state.SetSarahCarStarted(false);','    return state;','}','}'])
            (output/'HomeStory.h').write_text('\n'.join(header),encoding='utf-8')
    if world=='world-home':
        from .build_trigger_catalog import build as enrich_triggers
        result=enrich_triggers(output/'streaming_runtime.json',game_main,output)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--game-main',required=True)
    parser.add_argument('--pak-dir',action='append',required=True)
    parser.add_argument('--world',default='world-home')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=build(args.game_main,args.pak_dir,args.world,args.output)
    print(json.dumps({'regions':len(result['regions']),'worlds':result['runtime_packages'],
                      'warnings':result['warnings'],'symbols':len(result['symbols'])}))
