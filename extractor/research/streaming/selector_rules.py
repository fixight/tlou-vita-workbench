"""Readable path conditions from the decoded register/branch selectors."""


def conditions(selector, symbols):
    if selector['kind']=='constant':return [{'variant':selector['value'],'when':[]}]
    names={'0xf1360136':'taskComplete','0x4d2bf414':'beforeTask',
           '0x13e68c9f':'taskActive','0xa93d2926':'objectSpawned','0xf307e431':'getBoolean'}
    code=selector['instructions'];paths=[]
    def label(value):return symbols.get(value,{}).get('name',value) if isinstance(value,str) else str(value)
    def walk(pc,registers,tests,steps=0):
        if steps>128 or len(paths)>128:raise ValueError('Selector symbolic budget exceeded')
        inst=code[pc];op=inst['operation'];registers=list(registers)
        if op in ('resolve_symbol','symbol_id'):registers[inst['destination']]=inst['symbol_id']
        elif op=='integer':registers[inst['destination']]=inst['value']
        elif op=='copy_register':registers[inst['destination']]=registers[inst['source']]
        elif op in ('call_script','call_native'):
            fn=registers[inst['function_register']]
            args=', '.join(label(a) for a in registers[24:24+inst['argument_count']])
            registers[inst['destination']]=names.get(fn,label(fn))+'('+args+')'
        elif op=='jump':return walk(inst['target'],registers,tests,steps+1)
        elif op in ('jump_if_zero','jump_if_nonzero'):
            test=registers[inst['condition_register']]
            if isinstance(test,int):
                taken=bool(test)==(op=='jump_if_nonzero')
                return walk(inst['target'] if taken else pc+1,registers,tests,steps+1)
            negate=op=='jump_if_zero'
            walk(inst['target'],registers,tests+[('!' if negate else '')+test],steps+1)
            return walk(pc+1,registers,tests+[('' if negate else '!')+test],steps+1)
        elif op=='return':
            result=registers[inst['source']]
            if not isinstance(result,int):raise ValueError('Symbolic selector return is not an integer')
            paths.append({'variant':result,'when':tests});return
        else:raise ValueError('Unsupported symbolic selector instruction')
        walk(pc+1,registers,tests,steps+1)
    walk(0,[0]*40,[])
    return paths
