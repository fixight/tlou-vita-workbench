#pragma once
// TLTR v1: original region ordering and selector VM, independent of VitaGL.
// Coordinates are native Y-up metres. Resource readiness is owned by the host.
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace TlouStreaming {
using Id=uint32_t;
using Point=std::array<float,3>;
using Query=std::function<bool(Id,const std::vector<Id>&)>;
inline Id Hash(const std::string& s){Id h=0;for(unsigned char c:s){h^=Id(c)<<24;for(int i=0;i<8;++i)h=(h<<1)^((h&0x80000000u)?0x04c11db7u:0);}return h;}
enum class TaskStatus { Pending,Active,Complete };
struct StoryState {
    std::map<std::pair<Id,Id>,TaskStatus> tasks;
    std::map<Id,bool> spawned;
    std::map<std::pair<Id,Id>,bool> booleans; // property, object
    void SetTask(const std::string& chapter,const std::string& task,TaskStatus status){tasks[{Hash(chapter),Hash(task)}]=status;}
    // Original sarah-car start handler sets this exact boolean on the settings object.
    void SetSarahCarStarted(bool value=true){booleans[{0x4f12da44u,0x69c85a6du}]=value;}
    bool Ask(Id function,const std::vector<Id>& args) const {
        if(function==0xf1360136u || function==0x13e68c9fu || function==0x4d2bf414u){
            if(args.size()!=2)throw std::runtime_error("Task query arity");
            auto i=tasks.find({args[0],args[1]});if(i==tasks.end())throw std::runtime_error("Missing task state");
            return i->second==(function==0xf1360136u?TaskStatus::Complete:function==0x13e68c9fu?TaskStatus::Active:TaskStatus::Pending);
        }
        if(function==0xa93d2926u && args.size()==1){auto i=spawned.find(args[0]);if(i==spawned.end())throw std::runtime_error("Missing object state");return i->second;}
        if(function==0xf307e431u && args.size()==2){auto i=booleans.find({args[0],args[1]});if(i==booleans.end())throw std::runtime_error("Missing boolean state");return i->second;}
        throw std::runtime_error("Unsupported streaming query");
    }
};
struct Reader {
    const std::vector<uint8_t>& bytes;size_t pos=0;
    uint8_t Byte(){if(pos>=bytes.size())throw std::runtime_error("Truncated TLTR");return bytes[pos++];}
    uint32_t U32(){uint32_t n=0;for(unsigned i=0;i<4;++i)n|=uint32_t(Byte())<<(8*i);return n;}
    float Float(){uint32_t u=U32();float f;std::memcpy(&f,&u,4);if(!std::isfinite(f))throw std::runtime_error("Invalid TLTR float");return f;}
    uint32_t Count(){auto n=U32();if(n>1000000 || n>bytes.size()-pos)throw std::runtime_error("Invalid TLTR count");return n;}
    std::string Text(){auto n=Count();std::string s(bytes.begin()+pos,bytes.begin()+pos+n);pos+=n;return s;}
    std::vector<Id> Array(){auto n=Count();std::vector<Id> v;v.reserve(n);while(n--)v.push_back(U32());return v;}
};
struct Level {std::string name,file;std::vector<Id> dependencies;};
struct Selection {int region=-1;int variant=0;std::set<Id> display,resident;};
struct Instruction {uint8_t op,a,b,c;Id symbol;};
struct Region {
    std::string name;uint32_t flags;
    std::vector<std::vector<std::array<float,4>>> shapes;
    std::vector<Instruction> code;
    std::map<int,Selection> sets;
    bool Contains(const Point& p) const {
        for(const auto& shape:shapes){bool inside=!shape.empty();for(const auto& n:shape)if(double(n[0])*p[0]+double(n[1])*p[1]+double(n[2])*p[2]+n[3]>=0){inside=false;break;}if(inside)return true;}return false;
    }
    int Evaluate(const Query& query) const {
        std::array<Id,40> r{};size_t pc=0;
        for(int steps=0;steps<2048;++steps){
            if(pc>=code.size())throw std::runtime_error("Selector PC out of bounds");
            auto i=code[pc++];auto reg=[&](unsigned n)->Id& {if(n>=r.size())throw std::runtime_error("Selector register out of bounds");return r[n];};
            switch(i.op){
                case 0x15:case 0x44:reg(i.a)=i.symbol;break;
                case 0x0c:reg(i.a)=unsigned(i.b)|(unsigned(i.c)<<8);break;
                case 0x43:reg(i.a)=reg(i.b);break;
                case 0x1b:case 0x1c:{if(i.c>16)throw std::runtime_error("Selector arity");std::vector<Id> args(r.begin()+24,r.begin()+24+i.c);reg(i.a)=query(reg(i.b),args);break;}
                case 0x2d:pc=unsigned(i.a)|(unsigned(i.c)<<8);break;
                case 0x2e:if(reg(i.b))pc=unsigned(i.a)|(unsigned(i.c)<<8);break;
                case 0x2f:if(!reg(i.b))pc=unsigned(i.a)|(unsigned(i.c)<<8);break;
                case 0:return static_cast<int>(reg(i.b));
                default:throw std::runtime_error("Unsupported selector opcode");
            }
        }throw std::runtime_error("Selector instruction budget exceeded");
    }
};
struct World {
    std::string name;std::vector<Level> levels;std::vector<Region> regions;
    Point lower,extent;std::array<uint32_t,3> dims;
    std::vector<std::vector<Id>> cells;
    static World Load(const std::string& path){
        std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot open TLTR");
        std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(f)),{});Reader r{bytes};World w;
        if(r.U32()!=0x52544c54u || r.U32()!=1)throw std::runtime_error("Unsupported TLTR version");
        w.name=r.Text();
        auto n=r.Count();while(n--){Level l;l.name=r.Text();l.file=r.Text();l.dependencies=r.Array();w.levels.push_back(l);}
        n=r.Count();while(n--){Region v;v.name=r.Text();v.flags=r.U32();auto count=r.Count();
            while(count--){std::vector<std::array<float,4>> shape;auto faces=r.Count();if(faces<4)throw std::runtime_error("Invalid TLTR volume");while(faces--){std::array<float,4> plane;for(auto& f:plane)f=r.Float();shape.push_back(plane);}v.shapes.push_back(shape);}
            count=r.Count();while(count--){Instruction i;i.op=r.Byte();i.a=r.Byte();i.b=r.Byte();i.c=r.Byte();i.symbol=r.U32();v.code.push_back(i);}
            count=r.Count();while(count--){int variant=static_cast<int>(r.U32());Selection s;s.variant=variant;auto a=r.Array();s.display.insert(a.begin(),a.end());a=r.Array();s.resident.insert(a.begin(),a.end());v.sets.emplace(variant,s);}w.regions.push_back(v);
        }
        for(auto& f:w.lower)f=r.Float();
        for(auto& f:w.extent){f=r.Float();if(f<=0)throw std::runtime_error("Invalid grid extent");}
        uint64_t product=1;for(auto& d:w.dims){d=r.U32();if(d==0 || d>1000000)throw std::runtime_error("Invalid grid dimension");product*=d;if(product>1000000)throw std::runtime_error("Grid too large");}
        n=r.Count();if(n!=product+1)throw std::runtime_error("Invalid TLTR cells");while(n--)w.cells.push_back(r.Array());
        if(r.pos!=bytes.size())throw std::runtime_error("Trailing TLTR data");
        auto validLevels=[&](const auto& ids){for(auto id:ids)if(id>=w.levels.size())throw std::runtime_error("Invalid level index");};
        for(const auto& l:w.levels)validLevels(l.dependencies);
        for(const auto& v:w.regions)for(const auto& kv:v.sets){validLevels(kv.second.display);validLevels(kv.second.resident);}
        for(const auto& cell:w.cells)for(auto id:cell)if(id>=w.regions.size())throw std::runtime_error("Invalid region index");
        return w;
    }
    Selection Select(const Point& p,const Query& query,const std::map<Id,Selection>& overrides={}) const {
        uint32_t index=uint32_t(cells.size()-1);std::array<uint32_t,3> xyz{};bool inside=true;
        for(int i=0;i<3;++i){if(!std::isfinite(p[i]))throw std::runtime_error("Invalid camera position");double v=(double(p[i])-lower[i])/extent[i];if(v<0 || v>=1)inside=false;else xyz[i]=uint32_t(std::floor(v*dims[i]));}
        if(inside)index=(xyz[0]*dims[1]+xyz[1])*dims[2]+xyz[2];
        for(Id id:cells[index]){const auto& region=regions[id];if((region.flags&1) || !region.Contains(p))continue;
            auto over=overrides.find(id);if(over!=overrides.end()){auto s=over->second;s.region=int(id);return s;}
            int variant=region.Evaluate(query);if(variant<=0)continue;auto i=region.sets.find(variant);if(i==region.sets.end())throw std::runtime_error("Selector returned missing set");auto s=i->second;s.region=int(id);return s;
        }return {};
    }
    std::set<Id> Required(const Selection& s) const {
        std::set<Id> result;std::vector<Id> pending(s.display.begin(),s.display.end());pending.insert(pending.end(),s.resident.begin(),s.resident.end());
        while(!pending.empty()){Id i=pending.back();pending.pop_back();if(i>=levels.size())throw std::runtime_error("Invalid resource");if(!result.insert(i).second)continue;const auto& deps=levels[i].dependencies;pending.insert(pending.end(),deps.begin(),deps.end());}return result;
    }
};
struct Actions {bool outside=false,waiting=false;std::set<Id> load,show,hide,release;};
struct Planner {
    std::set<Id> visible,required;
    Actions Update(const World& world,const Selection& target,const std::set<Id>& ready,const std::set<Id>& pinned={}){
        Actions a;if(target.region<0){a.outside=true;return a;}
        auto next=world.Required(target);next.insert(pinned.begin(),pinned.end());
        for(Id id:next)if(!ready.count(id))a.load.insert(id);
        if(!a.load.empty()){a.waiting=true;return a;}
        for(Id id:target.display)if(!visible.count(id))a.show.insert(id);
        for(Id id:visible)if(!target.display.count(id))a.hide.insert(id);
        for(Id id:required)if(!next.count(id))a.release.insert(id);
        visible=target.display;required=next;return a;
    }
};
} // namespace TlouStreaming
