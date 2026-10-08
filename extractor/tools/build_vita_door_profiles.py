"""Compile saved native evidence into VDIP profiles bound to a specific LVL5."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tlou_extractor.vita_door_profiles import profile_from_evidence,write_profiles

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,default=Path(__file__).resolve().parents[1]/'research/door_interactions/profiles_plan.json')
    p.add_argument('--level',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    profiles=[]
    for item in json.loads(a.plan.read_text(encoding='utf-8')):
        evidence=json.loads((a.plan.parent/item['evidence']).read_text(encoding='utf-8'))
        profiles.append(profile_from_evidence(evidence,item['door_id'],item.get('locator')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    write_profiles(a.output,a.level.read_bytes(),profiles)
    print(f'Wrote {len(profiles)} native interaction profiles to {a.output}')

if __name__=='__main__':main()
