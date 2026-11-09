import {gasPassages} from './gas-passages.mjs';
import {THREE,materials as m,mesh,cylinder,ring,lathe,tube} from './models.mjs';
const pale=new THREE.MeshStandardMaterial({color:0xe7e0d1,roughness:.55});
const blue=new THREE.MeshStandardMaterial({color:0x487fb8,roughness:.5});
const red=new THREE.MeshStandardMaterial({color:0xa84c3b,roughness:.5});
function sleeve(g,outer,inner,height,mat,y=0){const o=lathe(g,[[outer,0],[outer,height],[inner,height],[inner,0],[outer,0]],mat);o.position.y=y;return o;}
function thread(g,r,y,length,mat=m.copper){const points=[];for(let i=0;i<=360;i++){const t=i/360;points.push(new THREE.Vector3(Math.cos(t*20*Math.PI)*r,y+t*length,Math.sin(t*20*Math.PI)*r));}mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),480,.014,8,false),mat,g);}
// The bore and radial ports are Boolean-cut meshes from the local Blender source.
function perforatedSleeve(g,key,mat=m.copper){
 const data=gasPassages[key],geometry=new THREE.BufferGeometry();
 geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));geometry.setIndex(data.indices);geometry.computeVertexNormals();
 return mesh(geometry,mat,g);
}
function bent(g){
 tube(g,[[0,-1,0],[0,-.35,0],[.12,.13,0],[.47,.57,0],[.8,.9,0]],.14,m.brass);
 sleeve(g,.18,.08,.27,m.brass,-1.05);thread(g,.18,-1.03,.21,m.brass);ring(g,.185,-.75,m.darkSteel,.018);
 const end=new THREE.Group();end.position.set(.8,.9,0);end.rotation.z=-Math.PI/4;g.add(end);sleeve(end,.145,.075,.23,m.copper);thread(end,.145,.015,.2);ring(end,.17,0,m.brass,.02);
}
function bundle(g,tig=false){
 // B40 p.2: control wires, water supply, power/water return, conduit and gas.
 // AQ20 p.2: gas, water, power cable and control wires; no MIG wire conduit.
 sleeve(g,.3,.245,1.65,m.rubber,-1.3);
 for(let i=0;i<23;i++)ring(g,.302,-1.25+i*.065,m.rubber,.008);
 const channels=tig?[
  {x:-.16,end:-.5,r:.065,mat:m.rubber},{x:0,end:0,r:.07,mat:blue},{x:.16,end:.5,r:.09,mat:red}
 ]:[
  {x:-.2,end:-.65,r:.065,mat:blue},{x:-.06,end:-.23,r:.085,mat:red},{x:.08,end:.23,r:.055,mat:m.darkSteel},{x:.2,end:.65,r:.06,mat:m.rubber}
 ];
 channels.forEach((c,i)=>{const top=1.55-(i%2)*.15;tube(g,[[c.x,.15,0],[c.x,.65,0],[c.end,1.0,.08],[c.end,top,.08]],c.r,c.mat);const fitting=new THREE.Group();fitting.position.set(c.end,top,.08);g.add(fitting);sleeve(fitting,c.r+.025,c.r*.65,.2,m.brass);thread(fitting,c.r+.025,.04,.13,m.brass);});
 for(let i=0;i<2;i++)tube(g,[[0,.1,-.14],[-.16,.8,-.17],[-.7-i*.12,1.65,-.15]],.018,m.rubber);
}
export function createPart(id,{inspection=true}={}){
 const g=new THREE.Group();g.userData.partId=id;
 switch(id){
 case 'mig-tip':
  // B40 p.3, position 23: rear thread, long copper shank, rounded outlet.
  lathe(g,[[.105,-.7],[.12,-.66],[.12,-.23],[.155,-.19],[.155,.58],[.12,.72],[.03,.75],[.03,-.7],[.105,-.7]],m.copper);thread(g,.122,-.64,.39);break;
 case 'mig-nozzle':
  // Position 24, tapered option: cylindrical rear and a distinct front taper.
  lathe(g,[[.35,-.8],[.37,-.76],[.37,.02],[.35,.1],[.25,.75],[.195,.75],[.285,.08],[.30,.02],[.30,-.8],[.35,-.8]],m.copper);ring(g,.365,-.74,m.darkSteel,.012);sleeve(g,.30,.255,.15,pale,-.79);break;
 case 'mig-diffuser':
  // Position 22: brass holder, black seals, blue-green collar, narrower nose.
  sleeve(g,.18,.075,.38,m.brass,-.08);sleeve(g,.18,.075,.32,m.brass,.5);
  perforatedSleeve(g,'mig',m.brass);
  sleeve(g,.29,.12,.18,m.brass,-.6);sleeve(g,.27,.12,.23,blue,-.42);sleeve(g,.27,.10,.1,m.brass,-.19);
  ring(g,.284,-.43,m.rubber,.018);ring(g,.276,-.2,m.rubber,.018);ring(g,.285,-.53,m.brass,.016);break;
 case 'mig-liner':{
  const points=[];for(let i=0;i<=1200;i++){const t=i/1200;const angle=t*140*Math.PI;points.push(new THREE.Vector3(.075*Math.cos(angle)+.22*Math.sin(t*Math.PI*2),-1.6+2.7*t,.075*Math.sin(angle)));}mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),1800,.018,6,false),m.steel,g);sleeve(g,.12,.065,.42,m.brass,1.05);thread(g,.12,1.15,.2,m.brass);break;}
 case 'mig-trigger':{
  const s=new THREE.Shape();s.moveTo(-.17,-.65);s.quadraticCurveTo(-.32,-.5,-.23,-.05);s.lineTo(-.15,.55);s.quadraticCurveTo(0,.75,.18,.55);s.lineTo(.23,-.4);s.quadraticCurveTo(.22,-.7,-.17,-.65);const hole=new THREE.Path();hole.absarc(0,.46,.055,0,Math.PI*2,true);s.holes.push(hole);mesh(new THREE.ExtrudeGeometry(s,{depth:.13,bevelEnabled:true,bevelSize:.025,bevelThickness:.025,bevelSegments:3,steps:1}),m.orange,g,0,0,-.065);for(let i=0;i<5;i++)mesh(new THREE.BoxGeometry(.26,.014,.01),m.grip,g,0,-.4+i*.065,.095);break;}
 case 'mig-neck':bent(g);break;
 case 'mig-cable':bundle(g);break;
 case 'tig-cup':
  lathe(g,[[.24,-.6],[.25,-.4],[.34,.4],[.34,.62],[.26,.62],[.25,.38],[.17,-.4],[.17,-.6],[.24,-.6]],m.ceramic);thread(g,.172,-.56,.25,pale);break;
 case 'tig-collet':{
  sleeve(g,.115,.055,.75,m.copper,-.7);for(let i=0;i<3;i++){const angle=i*Math.PI*2/3;const profile=[[.115,0],[.115,.66],[.055,.66],[.055,0],[.115,0]];const jaw=mesh(new THREE.LatheGeometry(profile.map(p=>new THREE.Vector2(...p)),24,angle+.025,Math.PI*2/3-.05),m.copper,g,0,.05); }ring(g,.118,-.66,m.copper,.018);break;}
 case 'tig-body':
  sleeve(g,.16,.065,.84,m.copper,-.65);thread(g,.17,-.6,.2);thread(g,.17,-.04,.23);ring(g,.20,-.22,m.copper,.018);perforatedSleeve(g,'tig');sleeve(g,.14,.065,.16,m.copper,.49);break;
 case 'tig-insulator':
  lathe(g,[[.36,-.17],[.39,-.13],[.39,.1],[.34,.2],[.2,.2],[.17,.13],[.17,-.17],[.36,-.17]],pale);ring(g,.385,-.06,pale,.016);break;
 case 'tig-backcap':
  lathe(g,[[0,-.9],[.095,-.9],[.14,-.8],[.14,.45],[.12,.5],[.05,.5],[.05,-.8],[0,-.8]],m.rubber);sleeve(g,.12,.05,.25,m.brass,.48);thread(g,.122,.49,.23,m.brass);ring(g,.15,.43,m.rubber,.024);for(let i=0;i<8;i++)ring(g,.142,.15+i*.032,m.grip,.009);break;
 case 'tig-head':{
  sleeve(g,.24,.13,.8,m.rubber,-.3);sleeve(g,.245,.13,.18,pale,.5);const neck=new THREE.Group();neck.rotation.z=-1.9;neck.position.y=-.1;g.add(neck);sleeve(neck,.14,.08,1.25,m.rubber);sleeve(neck,.15,.08,.2,m.brass,1.2);thread(neck,.15,1.23,.16,m.brass);break;}
 case 'tig-hoses':bundle(g,true);break;
 default:throw new Error(`Unknown part ${id}`);
 }
 g.traverse(o=>{if(o.isMesh){o.userData.partId=id;o.material=o.material.clone();}});
 if(inspection){g.rotation.set(.35,-.4,-.9);g.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(g);g.position.sub(box.getCenter(new THREE.Vector3()));}return g;
}
