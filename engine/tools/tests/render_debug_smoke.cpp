#include <cassert>
#include <cmath>
#include <cstdio>
#include "Engine/Render.h"
#include "Engine/DebugHud.h"
#include "Engine/DebugHudText.h"
#include "Objects/Character.h"
#include <psp2/ctrl.h>

int main(int argc,char** argv){
    assert(argc==2);
    assert(HudUnsigned(18446744073709551615ULL)=="18446744073709551615");
    assert(HudFixed(21.234,1)=="21.2" && HudFixed(9.999,2)=="10.00" && HudFixed(-1.25,2)=="-1.25");
    RenderStats textStats;textStats.drawCalls=125;textStats.triangles=123456789012ULL;textStats.vertices=370370367036ULL;
    const auto sample=BuildHudText(21.23,47.1,2.51,0,textStats,1888,true);
    assert(sample.find("FPS 21.2  FRAME 47.10 MS  SUBMIT 2.51 MS")!=std::string::npos);
    assert(sample.find("SCENE DRAWS 125  TRIANGLES 123456789012  VERTICES 370370367036")!=std::string::npos);
    assert(sample.find("NOCLIP ON  GRAVITY/COLLISION OFF  PHYSICS 0.00 MS (1888 TRIS)")!=std::string::npos);
    assert(sample.find("(NULL)")==std::string::npos);
    CameraActor camera;
    camera.SetPosition(0,0,0);
    Mesh mesh;mesh.vertexCount=6;mesh.vboID=7;
    Texture tex;tex.textureID=42;tex.size_x=64;tex.size_y=64;
    Instance inside{};inside.mesh=&mesh;inside.texture=&tex;
    inside.modelMatrix=glm::translate(glm::mat4(1),glm::vec3(0,0,-5));
    inside.boundingBox.minBounds=glm::vec3(-1,-1,-6);
    inside.boundingBox.maxBounds=glm::vec3(1,1,-4);
    Instance distant=inside;distant.modelMatrix[3]=glm::vec4(1000,0,-5,1);
    Instance offscreen=inside;offscreen.modelMatrix[3]=glm::vec4(20,0,-5,1);
    offscreen.boundingBox.minBounds.x=19;offscreen.boundingBox.maxBounds.x=21;
    Instance invalid{};
    std::vector<Instance> objects{inside,distant,offscreen,invalid};
    Render renderer;renderer.BeginFrame();
    gExpectSceneTexture=true;
    renderer.render(objects,&camera,{},1);
    auto stats=renderer.GetStats();
    assert(stats.objectsTested==4 && stats.drawCalls==1 && stats.objectsDrawn==1);
    assert(stats.vertices==6 && stats.triangles==2);
    assert(stats.culledDistance==1 && stats.culledFrustum==1 && stats.invalidObjects==1);
    assert(stats.textureBinds==1 && stats.vboBinds==1 && stats.visibleTextureBytes==16384);
    // Pass boundaries unbind GL resources; the next pass must rebind them.
    objects={inside};renderer.render(objects,&camera,{},1);
    assert(renderer.GetStats().drawCalls==2 && renderer.GetStats().textureBinds==2);
    assert(renderer.GetStats().visibleTextureBytes==16384);
    renderer.BeginFrame();renderer.render(objects,&camera,{},1);
    assert(renderer.GetStats().drawCalls==1 && renderer.GetStats().textureBinds==1);
    gExpectSceneTexture=false;
    DebugHud hud;assert(hud.Init());
    auto before=gDrawCalls;
    hud.Draw(.5,1.2,0,renderer.GetStats(),9561,true);
    assert(gDrawCalls==before+1 && renderer.GetStats().drawCalls==1);
    assert(gLastDrawVertices>6 && gLastDrawVertices<=8192);
    before=gDrawCalls;
    hud.Draw(.5,1.2,0,renderer.GetStats(),9561,true,
             "TRIGGERS 1/83  PROBE CAMERA\nHOM-HOUSE-RGN-EXPLOSION-DOWNSTAIRS-1\nLAST ENTER: TEST_TRIGGER\n");
    assert(gDrawCalls==before+1 && gLastDrawVertices<=8192);


    Character character;character.SetCamera(&camera);
    character.SetPosition(0,10,0);character.SetVelocity(3,-2,4);
    camera.SetMode(CameraMode::Spectate);
    character.Update(1);
    assert(character.GetPosition().x==0 && character.GetPosition().y==10 && character.GetPosition().z==0);
    assert(character.GetVelocity().x==0 && character.GetVelocity().y==0 && character.GetVelocity().z==0);
    camera.SetMode(CameraMode::ThirdPerson);character.Update(.5f);
    assert(std::abs(character.GetPosition().y-9.7f)<1e-5f);
    // A door action faces the target and temporarily suppresses movement input.
    character.SetPosition(0,10,0);character.SetVelocity(0,0,0);
    character.StartDoorInteraction({1,10,0});assert(character.IsInteracting());
    assert(std::abs(character.GetRotation().y+90.f)<1e-5f);
    gPad.lx=255;gPad.ly=128;character.Update(.5f);
    assert(character.GetPosition().x==0&&character.GetPosition().z==0);
    character.Update(1.f);assert(!character.IsInteracting());
    character.Update(.1f);assert(std::abs(character.GetPosition().x)+std::abs(character.GetPosition().z)>.01f);
    gPad.lx=128;
    // SELECT toggles noclip once per press, not on every held frame.
    gPad.buttons=SCE_CTRL_SELECT;camera.Update(0);assert(camera.GetMode()==CameraMode::Spectate);
    camera.Update(0);assert(camera.GetMode()==CameraMode::Spectate);
    gPad.buttons=0;camera.Update(0);gPad.buttons=SCE_CTRL_SELECT;camera.Update(0);
    assert(camera.GetMode()==CameraMode::ThirdPerson);


    // Real trigger-view code: cap visible areas, cull far/behind/huge areas, isolate focus.
    TriggerManager triggers;assert(triggers.Load(argv[1]));
    CameraActor viewCamera;viewCamera.SetPosition(0,0,0);
    TriggerDebugView view;assert(view.Init());
    assert(TriggerDebugView::ShortName("hom-house-rgn-explosion-downstairs-1")=="EXPLOSION DOWNSTAIRS 1");
    before=gDrawCalls;view.Draw(triggers,&viewCamera,false);
    assert(gDrawCalls==before+1 && gLastDrawVertices==72);
    assert(view.GetLabels().size()==3);
    for(const auto& label:view.GetLabels())assert(label.text.find("FAR")==std::string::npos&&label.text.find("BEHIND")==std::string::npos);
    for(size_t i=0;i<view.GetLabels().size();++i)for(size_t j=0;j<i;++j)
        assert(std::abs(view.GetLabels()[i].y-view.GetLabels()[j].y)>=24);
    view.CycleMode();assert(view.GetMode()==2);view.Draw(triggers,&viewCamera,true);
    assert(gLastDrawVertices==24 && view.GetLabels().size()==1);
    triggers.Update({{0,0,-5},{0,0,-5}});view.Draw(triggers,&viewCamera,true);
    assert(view.GetLabels()[0].text.find("INSIDE")!=std::string::npos);
    before=gDrawCalls;hud.Draw(.5,1.2,0,renderer.GetStats(),9561,true,"",view.GetLabels(),false);
    assert(gDrawCalls==before+1 && gLastDrawVertices<=8192);
    view.CycleMode();before=gDrawCalls;view.Draw(triggers,&viewCamera,true);
    assert(view.GetMode()==0&&view.GetLabels().empty()&&gDrawCalls==before);
    view.CycleMode();assert(view.GetMode()==1);
    RenderStats heavy;heavy.drawCalls=2000;heavy.vertices=1000000;
    auto lightEstimate=EstimateVitaFps(RenderStats{}),heavyEstimate=EstimateVitaFps(heavy);
    assert(heavyEstimate.low<=heavyEstimate.high && heavyEstimate.high<=60);
    assert(heavyEstimate.low<lightEstimate.low && heavyEstimate.high<lightEstimate.high);
    puts("PASS: submitted draws/culling, resource rebinding, HUD one draw, noclip freeze/resume, SELECT debounce, model monotonicity, trigger view cap/culling/focus/off/labels");
}
