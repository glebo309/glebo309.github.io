import {THREE,materials as m,mesh,cylinder,ring,lathe,tube} from './models.mjs';
const pale=new THREE.MeshStandardMaterial({color:0xe7e0d1,roughness:.55});
const blue=new THREE.MeshStandardMaterial({color:0x487fb8,roughness:.5});
const red=new THREE.MeshStandardMaterial({color:0xa84c3b,roughness:.5});
function sleeve(g,outer,inner,height,mat,y=0){const o=lathe(g,[[outer,0],[outer,height],[inner,height],[inner,0],[outer,0]],mat);o.position.y=y;return o;}
function thread(g,r,y,length,mat=m.copper){const points=[];for(let i=0;i<=360;i++){const t=i/360;points.push(new THREE.Vector3(Math.cos(t*20*Math.PI)*r,y+t*length,Math.sin(t*20*Math.PI)*r));}mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),480,.014,8,false),mat,g);}
function ports(g,r,y){for(let i=0;i<6;i++){const a=i*Math.PI/3;const port=mesh(new THREE.CircleGeometry(.045,24),m.rubber,g,Math.sin(a)*(r+.001),y,Math.cos(a)*(r+.001));port.rotation.y=a;}}
function bent(g,mat=m.brass){tube(g,[[0,-1,0],[0,-.35,0],[.2,.1,0],[.65,.45,0],[1,.6,0]],.14,mat);const end=new THREE.Group();end.position.set(1,.6,0);end.rotation.z=-1.1;g.add(end);sleeve(end,.17,.075,.35,mat);thread(end,.17,.05,.23);ring(end,.18,.02,m.darkSteel);}
function bundle(g,tig=false){const shell=sleeve(g,.3,.245,1.65,tig?blue:m.rubber,-1.3);shell.rotation.z=.2;for(let i=0;i<24;i++)ring(g,.302,-1.2+i*.065,m.rubber,.009).rotation.z=.2;const colors=[blue,red,m.rubber,m.darkSteel];for(let i=0;i<4;i++){const x=(i-1.5)*.16;const end=(i-1.5)*.4;tube(g,[[x,.1,0],[x,.6,0],[end,1.05,.12],[end,1.7-i*.12,.12]],i===3?.04:.08,colors[i]);const fitting=new THREE.Group();fitting.position.set(end,1.7-i*.12,.12);g.add(fitting);sleeve(fitting,.095,.055,.22,m.brass);thread(fitting,.096,.05,.14,m.brass);}for(let i=0;i<2;i++)tube(g,[[.1*i,.2,.13],[.15*i,.9,.16],[.6+i*.12,1.7,.15]],.018,m.rubber);}
export function createPart(id){
 const g=new THREE.Group();g.userData.partId=id;
 switch(id){
 case 'mig-tip':
  lathe(g,[[.12,-.7],[.14,-.67],[.14,-.2],[.18,-.16],[.18,.55],[.14,.75],[.035,.75],[.035,-.7],[.12,-.7]],m.copper);thread(g,.145,-.65,.45);break;
 case 'mig-nozzle':
  lathe(g,[[.35,-.65],[.38,-.6],[.38,-.2],[.32,.65],[.25,.65],[.28,-.2],[.29,-.65],[.35,-.65]],m.copper);ring(g,.38,-.5,m.steel,.018);sleeve(g,.29,.24,.16,pale,-.67);break;
 case 'mig-diffuser':
  sleeve(g,.18,.075,1.2,m.brass,-.6);sleeve(g,.25,.08,.2,m.darkSteel,-.6);sleeve(g,.24,.08,.2,blue,-.4);thread(g,.18,.36,.24,m.brass);ports(g,.18,.1);break;
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
  sleeve(g,.16,.065,1.3,m.copper,-.65);thread(g,.17,-.6,.75);ring(g,.22,.14,m.copper,.025);ports(g,.16,.36);break;
 case 'tig-insulator':
  lathe(g,[[.36,-.17],[.39,-.13],[.39,.1],[.34,.2],[.2,.2],[.17,.13],[.17,-.17],[.36,-.17]],pale);ring(g,.385,-.06,pale,.016);break;
 case 'tig-backcap':
  lathe(g,[[0,-.9],[.095,-.9],[.14,-.8],[.14,.45],[.12,.5],[.05,.5],[.05,-.8],[0,-.8]],m.rubber);sleeve(g,.12,.05,.25,m.brass,.48);thread(g,.122,.49,.23,m.brass);ring(g,.15,.43,m.rubber,.024);for(let i=0;i<8;i++)ring(g,.142,.15+i*.032,m.grip,.009);break;
 case 'tig-head':{
  sleeve(g,.24,.13,.8,m.rubber,-.3);sleeve(g,.245,.13,.18,pale,.5);const neck=new THREE.Group();neck.rotation.z=-1.9;neck.position.y=-.1;g.add(neck);sleeve(neck,.14,.08,1.25,m.rubber);sleeve(neck,.15,.08,.2,m.brass,1.2);thread(neck,.15,1.23,.16,m.brass);break;}
 case 'tig-hoses':bundle(g,true);break;
 default:throw new Error(`Unknown part ${id}`);
 }
 g.rotation.set(.35,-.4,-.9);g.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(g);g.position.sub(box.getCenter(new THREE.Vector3()));return g;
}
