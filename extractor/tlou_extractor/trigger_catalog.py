"""Evidence-backed region cards and symbolic event calls, never a gameplay VM."""
import copy
import json
import struct
from collections import Counter


def symbol(value, labels):
    item={'kind':'symbol','id':value}
    if value in labels:
        item.update(name=labels[value]['name'],spelling_source=labels[value]['source'])
    return item


def expression_text(value):
    kind=value.get('kind')
    if kind=='symbol':return value.get('name',value['id'])
    if kind=='integer':return str(value['value'])
    if kind=='call_result':return value.get('function','?')+'('+', '.join(expression_text(a) for a in value.get('arguments',[]))+')'
    return '?'


def callback_calls(program, labels):
    """Trace bounded control-flow paths, retaining guards and unresolved operands.

    Unknown instructions invalidate register knowledge; no guessed opcode or
    game-state value is used to turn a partial callback into an unconditional action.
    """
    code=program.get('instructions',[])
    if not code:return {'calls':[],'limitations':['No instruction array available']}
    pending=[(0,{},[],set())];calls=[];limitations=set();seen_calls=set();steps=0
    while pending and steps<4096:
        pc,registers,guards,visited=pending.pop()
        while 0<=pc<len(code) and steps<4096:
            steps+=1
            if pc in visited:
                limitations.add('Loop body truncated; callback is not executed');break
            visited=visited|{pc};inst=code[pc];op=inst['operation']
            unknown={'kind':'unresolved'}
            if op in ('resolve_symbol','symbol_id'):
                registers[inst['destination']]=symbol(inst['symbol_id'],labels)
            elif op=='integer':registers[inst['destination']]={'kind':'integer','value':inst['value']}
            elif op=='copy_register':registers[inst['destination']]=copy.deepcopy(registers.get(inst['source'],unknown))
            elif op in ('call_native','call_script'):
                fn=copy.deepcopy(registers.get(inst['function_register'],unknown))
                args=[copy.deepcopy(registers.get(i,unknown)) for i in range(24,24+inst['argument_count'])]
                call={'pc':pc,'source_offset':inst['offset'],'dispatch':op,'function':fn,
                      'arguments':args,'guards':copy.deepcopy(guards)}
                name=fn.get('name')
                if name=='send-event' and len(args)>=2:
                    call['event']=args[0];call['target']=args[1]
                elif name=='set-boolean' and len(args)==3:
                    call.update(property=args[0],value=args[1],target=args[2])
                call['text']=expression_text(fn)+'('+', '.join(expression_text(a) for a in args)+')'
                signature=json.dumps(call,sort_keys=True)
                if signature not in seen_calls:seen_calls.add(signature);calls.append(call)
                registers[inst['destination']]={'kind':'call_result','function':expression_text(fn),'arguments':copy.deepcopy(args),'call_pc':pc}
            elif op=='return':break
            elif op=='jump':pc=inst['target'];continue
            elif op in ('jump_if_zero','jump_if_nonzero'):
                condition=copy.deepcopy(registers.get(inst['condition_register'],unknown))
                nonzero=op=='jump_if_nonzero'
                if condition.get('kind')=='integer':
                    if bool(condition['value'])==nonzero:pc=inst['target'];continue
                else:
                    if len(pending)>=128:
                        limitations.add('Branch budget exceeded');break
                    pending.append((inst['target'],copy.deepcopy(registers),
                                    guards+[{'condition':condition,'nonzero':nonzero}],set(visited)))
                    guards=guards+[{'condition':condition,'nonzero':not nonzero}]
            else:
                limitations.add('Unknown instruction '+inst['opcode']+' at pc '+str(pc))
                registers={}
            pc+=1
    if steps>=4096:limitations.add('Instruction budget exceeded')
    return {'calls':calls,'limitations':sorted(limitations)}


CATEGORY_LABELS={
    'streaming':'Стриминг чанков','audio_zone':'Звуковая область',
    'reflection':'Отражения','dialogue':'Диалог / реплики',
    'effects':'Эффекты','gameplay':'Сценарное событие','spatial':'Область без callback'}


def classify(region):
    name=region['name'].lower();source=region['source_level']
    if region['type']=='streaming_region':return 'streaming','streaming properties'
    if 'reflection' in name:return 'reflection','original region name'
    if source.endswith('-audio'):return 'audio_zone','original audio PAK; not necessarily PlaySound'
    if 'vox' in name:return 'dialogue','original region name; behaviour needs port handler'
    if source.endswith('-fx') or name.startswith(('fx-','fx_')):return 'effects','original name/source'
    if region.get('callbacks'):return 'gameplay','original callback records'
    return 'spatial','no callback in REGION_TREE; other controllers may use this region'


def binding_from_properties(obj):
    """Explicitly authored port action. Not inferred original game behaviour."""
    if not obj.get('nd_cpp_enabled',False):return None
    action=str(obj.get('nd_cpp_action','')).strip()
    phase=str(obj.get('nd_cpp_phase','enter')).strip()
    if not action or not action.isascii() or not all(c.isalnum() or c=='_' for c in action) or action[0].isdigit():
        raise ValueError('C++ action must be a nonempty ASCII identifier: '+obj.name)
    if phase not in ('enter','inside','exit'):raise ValueError('Trigger phase must be enter, inside or exit: '+obj.name)
    parameters=json.loads(str(obj.get('nd_cpp_parameters','{}')))
    if not isinstance(parameters,dict):raise ValueError('Trigger parameters must be a JSON object: '+obj.name)
    json.dumps(parameters,allow_nan=False)
    return {'action':action,'phase':phase,'once':bool(obj.get('nd_cpp_once',False)),
            'target_id':str(obj.get('nd_cpp_target','')).strip() or None,
            'parameters':parameters,'origin':'authored_port_binding'}


def build_catalog(document):
    labels=document.get('symbols',{});contexts=document.get('controller_contexts',{})
    entries=[]
    for region in document['regions']:
        category,basis=classify(region);callbacks=[];targets={}
        for cb in region.get('callbacks',[]):
            trace=callback_calls(cb['program'],labels)
            trace.update(phase=cb['phase'],event_key=cb['event_key'],payload_offset=cb['program'].get('payload_offset'))
            callbacks.append(trace)
            for call in trace['calls']:
                target=call.get('target',{})
                if target.get('kind')=='symbol':targets[target['id']]=target
        controllers=[]
        for target in targets.values():
            template=target.get('name','').rsplit('-',1)[0]
            if template in contexts:controllers.append(dict(target=target,**contexts[template]))
        properties=[]
        for prop in region['properties']:
            row=dict(prop);row['key_name']=labels.get(prop['key_raw'],{}).get('name')
            if prop.get('value_type')==4 and prop.get('value_raw_hex'):
                raw=bytes.fromhex(prop['value_raw_hex'])
                value=f'0x{struct.unpack_from("<I",raw)[0]:08x}'
                row['raw_word']=value
                if value in labels:row['matched_symbol']=symbol(value,labels)
            properties.append(row)
        card={'id':region['id'],'source_level':region['source_level'],'name':region['name'],
              'source_file':region['source_file'],'source_offset':region['offset'],
              'source_id':region['name_id_raw'],'native_flags':region.get('native_flags',0),
              'category':category,'category_label':CATEGORY_LABELS[category],'category_basis':basis,
              'volumes':[{'kind':s.get('analytic',{}).get('kind','convex'),
                          'min':s['bounds_min'],'max':s['bounds_max']} for s in region['shapes']],
              'properties':properties,'callbacks':callbacks,'targets':list(targets.values()),
              'controller_contexts':controllers,'port_binding':region.get('port_binding'),
              'notes':['Категория определена по исходному имени/PAK; она не доказывает полный эффект области.',
                       'Имена состояний контроллера не задают порядок выполнения или тайминги.']}
        entries.append(card)
    return {'schema':'tlou.trigger_catalog','version':1,'coordinate_system':'native_y_up',
            'statistics':{'regions':len(entries),'with_callbacks':sum(bool(e['callbacks']) for e in entries),
                          'categories':dict(Counter(e['category'] for e in entries))},
            'triggers':entries}


def card_text(card):
    lines=[card['id'],card['category_label'],
           f"Источник: {card['source_file']} @ {card['source_offset']:#x}",
           'Исходный ID: '+card['source_id'],'Исходные флаги: '+hex(card['native_flags']),
           'Основание категории: '+card['category_basis']]
    for index,volume in enumerate(card['volumes']):
        lines.append(f"Объём {index}: {volume['kind']}; min={volume['min']}; max={volume['max']} (Y вверх)")
    if card['properties']:lines.append('\nИсходные свойства:')
    for prop in card['properties']:
        key=prop.get('key_name') or prop['key_raw']
        value=prop.get('value',prop.get('raw_word',prop.get('value_raw_hex','?')))
        matched='; совпадение CRC: '+expression_text(prop['matched_symbol']) if prop.get('matched_symbol') else ''
        lines.append('  '+key+' = '+str(value)+matched)
    for callback in card['callbacks']:
        lines.append('\n'+callback['phase'].upper()+' '+callback['event_key'])
        for call in callback['calls']:
            guard=' [условный вызов]' if call['guards'] else ''
            lines.append('  '+call['text']+guard)
            for condition in call['guards']:
                lines.append('    Условие: '+expression_text(condition['condition'])+(' != 0' if condition['nonzero'] else ' == 0'))
        lines.extend('  Ограничение: '+note for note in callback['limitations'])
    if not card['callbacks']:lines.append('\nВ REGION_TREE нет callback. Это не доказывает отсутствие поведения.')
    for context in card['controller_contexts']:
        lines.append('\nКонтроллер: '+expression_text(context['target'])+' — '+context['source'])
        lines.extend('  '+h['state']+' / '+h['phase'] for h in context['handlers'])
    if card.get('port_binding'):lines.append('\nНазначение для порта: '+json.dumps(card['port_binding'],ensure_ascii=False))
    lines.extend('\n'+note for note in card['notes'])
    return '\n'.join(lines)
