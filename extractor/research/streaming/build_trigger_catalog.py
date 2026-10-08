"""Enrich region triggers from original script spellings and debug state labels."""
import argparse
import json
import re
import struct
from pathlib import Path
from .psarc import Psarc
from .build_runtime import symbols
from tlou_extractor.trigger_catalog import build_catalog, card_text


def crc_table():
    result=[]
    for value in range(256):
        h=value<<24
        for _ in range(8):h=((h<<1)^(0x04c11db7 if h&0x80000000 else 0))&0xffffffff
        result.append(h)
    return result


def scan_archive(archive,wanted,script_prefix):
    table=crc_table();cache={};found={};contexts={};scanned=0
    for name in archive.names:
        if not name.startswith('dc1/') or not name.endswith('.bin'):continue
        data=archive.read(name);scanned+=1
        for span in re.finditer(rb'[\x20-\x7e]{3,}',data):
            for token in re.finditer(rb'[a-zA-Z*][a-zA-Z0-9_?!+*/.:-]{1,100}',span.group()):
                raw=token.group()
                if raw not in cache:
                    h=0
                    for byte in raw:h=((h<<8)&0xffffffff)^table[(h>>24)^byte]
                    cache[raw]=f'0x{h:08x}'
                key=cache[raw]
                if key in wanted:
                    text=raw.decode('ascii')
                    found.setdefault(key,{}).setdefault(text,{'name':text,'source':name,
                        'offset':span.start()+token.start(),'evidence':'original printable token matches symbol CRC'})
            if name.startswith(script_prefix):
                for match in re.finditer(rb'([a-zA-Z][a-zA-Z0-9_-]+) ([a-zA-Z0-9_!?-]+) \(on \((start|end|update|event)\)\)',span.group()):
                    template,state,phase=(v.decode('ascii') for v in match.groups())
                    context=contexts.setdefault(template,{'source':name,'handlers':[]})
                    context['handlers'].append({'state':state,'phase':phase,'offset':span.start()+match.start()})
    resolved={key:next(iter(options.values())) for key,options in found.items() if len(options)==1}
    collisions={key:list(options) for key,options in found.items() if len(options)>1}
    return resolved,contexts,{'dc_files_scanned':scanned,'ambiguous_spellings':collisions}


def build(bundle,game_main,output,script_prefix='dc1/ss-home/',family='hom'):
    document=json.loads(Path(bundle).read_text(encoding='utf-8'))
    wanted=set(re.findall(r'0x[0-9a-f]{8}',json.dumps(document)))
    for region in document['regions']:
        for prop in region['properties']:
            if prop['value_type']==4 and prop.get('value_raw_hex'):
                wanted.add(f'0x{struct.unpack_from("<I",bytes.fromhex(prop["value_raw_hex"]))[0]:08x}')
    archive=Psarc(Path(game_main)/'bin.psarc')
    labels,contexts,scan=scan_archive(archive,wanted,script_prefix)
    eboot=Path(game_main).parents[2]/'eboot.bin'
    if eboot.exists():labels.update(symbols(eboot.read_bytes(),wanted,'eboot.bin'))
    old_labels=document.get('symbols',{})
    new_labels={k:v for k,v in labels.items() if k not in old_labels}
    # Retain original source locations for already recovered spellings.
    document['symbols']={**labels,**old_labels}
    document['controller_contexts']=contexts
    catalog=build_catalog(document)
    catalog['symbol_scan']=dict(scan,new_symbols=len(new_labels),matched_symbols=len(labels),controller_templates=len(contexts))
    document['trigger_catalog']=catalog
    destination=Path(output);destination.mkdir(parents=True,exist_ok=True)
    (destination/'trigger_catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'trigger_symbols.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'streaming_runtime.json').write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    cards=[e for e in catalog['triggers'] if e['source_level'].startswith(family+'-')]
    lines=['# Области пролога: каталог для сборки порта','',
           f'Областей: {len(cards)}. С callback: {sum(bool(e["callbacks"]) for e in cards)}.',
           '','Формы, события, аргументы и получатели извлечены из исходных файлов.',
           'Категории по имени/PAK — подсказки. Имена состояний контроллера не доказывают порядок и тайминги.',
           'Назначение C++ для порта задаётся отдельно, исходные callback не исполняются.',
           '','## Сценарные области с событиями','']
    for card in cards:
        if card['callbacks'] and card['category']!='reflection':
            lines.extend(['### '+card['id'],'','```text',card_text(card),'```',''])
    lines.extend(['## Все области','', '| Область | Категория | События |','|---|---|---|'])
    for card in cards:
        phases=', '.join(c['phase'] for c in card['callbacks']) or 'нет callback'
        lines.append('| '+card['id']+' | '+card['category_label']+' | '+phases+' |')
    (destination/'prologue_triggers.md').write_text('\n'.join(lines),encoding='utf-8')
    return document


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',required=True);parser.add_argument('--game-main',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--script-prefix',default='dc1/ss-home/');parser.add_argument('--family',default='hom')
    args=parser.parse_args()
    document=build(args.bundle,args.game_main,args.output,args.script_prefix,args.family)
    print(json.dumps(document['trigger_catalog']['statistics']))
    print(json.dumps(document['trigger_catalog']['symbol_scan']))
