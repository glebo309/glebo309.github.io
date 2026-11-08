import * as THREE from '../assets/three.module.js';
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const materials={
 rubber:new THREE.MeshStandardMaterial({color:0x171b18,roughness:.68,metalness:.08}),
 grip:new THREE.MeshStandardMaterial({color:0x353d36,roughness:.52,metalness:.15}),
 orange:new THREE.MeshStandardMaterial({color:0xf56630,roughness:.35,metalness:.12}),
 steel:new THREE.MeshStandardMaterial({color:0xbac0b7,roughness:.21,metalness:1}),
 darkSteel:new THREE.MeshStandardMaterial({color:0x565e55,roughness:.32,metalness:1}),
 copper:new THREE.MeshStandardMaterial({color:0xc28a55,roughness:.24,metalness:1}),
 brass:new THREE.MeshStandardMaterial({color:0xc7ac69,roughness:.28,metalness:1}),
 ceramic:new THREE.MeshStandardMaterial({color:0xc89493,roughness:.5,metalness:0}),
};
const v=(x,y,z=0)=>new THREE.Vector3(x,y,z);
function mesh(geo,mat,parent,x=0,y=0,z=0){const m=new THREE.Mesh(geo,mat);m.position.set(x,y,z);parent.add(m);return m;}
function cylinder(parent,r1,r2,height,mat,y,x=0,z=0){return mesh(new THREE.CylinderGeometry(r1,r2,height,64),mat,parent,x,y,z);}
function ring(parent,r,y,mat=materials.darkSteel,tube=.025){const m=mesh(new THREE.TorusGeometry(r,tube,12,64),mat,parent,0,y,0);m.rotation.x=Math.PI/2;return m;}
function lathe(parent,points,mat){return mesh(new THREE.LatheGeometry(points.map(p=>new THREE.Vector2(...p)),64),mat,parent);}
function tube(parent,points,r,mat){const curve=new THREE.CatmullRomCurve3(points.map(p=>v(...p)));return mesh(new THREE.TubeGeometry(curve,64,r,16,false),mat,parent);}
function makeTorch(type='mig',cable=true){
 const group=new THREE.Group();const body=new THREE.Group();group.add(body);
 const handle=lathe(body,[[.15,-1.9],[.25,-1.87],[.31,-1.7],[.34,-1.35],[.35,-.65],[.3,-.18],[.24,.08],[.18,.13]],materials.rubber);
 handle.scale.z=.79;
 const inset=lathe(body,[[.17,-1.75],[.255,-1.6],[.285,-1.25],[.29,-.7],[.255,-.35],[.19,-.2]],materials.grip);inset.scale.z=.86;
 for(let i=0;i<13;i++){const y=-1.55+i*.09;const r=.28+Math.sin(i/13*Math.PI)*.014;const rib=ring(body,r,y,materials.rubber,.021);rib.scale.z=.85;}
 const strip=mesh(new THREE.BoxGeometry(.063,1.36,.035),materials.orange,body,.235,-.95,.19);strip.rotation.z=.035;
 const strip2=strip.clone();strip2.position.x=-.235;body.add(strip2);
 cylinder(body,.205,.25,.14,materials.orange,-.12);cylinder(body,.17,.2,.19,materials.rubber,.04);
 const trigger=mesh(new THREE.BoxGeometry(.23,.64,.14),materials.orange,body,0,-.54,.27);trigger.rotation.x=-.13;
 for(const y of [-1.6,-.25]){const screw=mesh(new THREE.CylinderGeometry(.031,.031,.015,16),materials.steel,body,0,y,.266);screw.rotation.x=Math.PI/2;}
 for(let i=0;i<7;i++)cylinder(body,.145-i*.004,.15-i*.004,.09,materials.rubber,-1.94-i*.09);
 if(cable)tube(body,[[0,-2.5,0],[.02,-2.8,0],[.3,-3.3,.02],[1.1,-3.8,-.1],[2.0,-3.9,-.3]],.105,materials.rubber);
 const labelCanvas=document.createElement('canvas');labelCanvas.width=256;labelCanvas.height=64;const ctx=labelCanvas.getContext('2d');ctx.fillStyle='#b4c0b0';ctx.font='bold 40px Arial';ctx.textAlign='center';ctx.fillText('BORIS',128,44);const tex=new THREE.CanvasTexture(labelCanvas);tex.colorSpace=THREE.SRGBColorSpace;const logo=mesh(new THREE.PlaneGeometry(.37,.093),new THREE.MeshBasicMaterial({map:tex,transparent:true}),body,0,-1.29,.292);
 const parts=[];
 if(type==='mig'){
 tube(body,[[0,.13,0],[0,.55,0],[.13,.85,0],[.4,1.1,0],[.57,1.29,0]],.12,materials.darkSteel);
 tube(body,[[0,.2,0],[0,.54,0],[.13,.84,0],[.4,1.09,0],[.57,1.29,0]],.094,materials.steel);
 ring(body,.15,.25,materials.rubber,.035);
 const head=new THREE.Group();head.position.set(.57,1.29,0);head.rotation.z=-.65;body.add(head);
 const holder=new THREE.Group();head.add(holder);cylinder(holder,.157,.14,.5,materials.brass,.24);for(let i=0;i<8;i++)ring(holder,.159,.08+i*.045,materials.copper,.009);cylinder(holder,.185,.185,.12,materials.darkSteel,.02);
 const tip=new THREE.Group();head.add(tip);cylinder(tip,.062,.08,.48,materials.copper,.56);cylinder(tip,.026,.026,.012,materials.rubber,.805);for(let i=0;i<4;i++)ring(tip,.08,.35+i*.025,materials.brass,.009);
 const nozzle=new THREE.Group();head.add(nozzle);lathe(nozzle,[[.20,.12],[.225,.16],[.225,.35],[.215,.45],[.178,.92],[.17,.97],[.133,.97],[.136,.9],[.17,.43],[.177,.35],[.177,.16],[.20,.12]],materials.copper);ring(nozzle,.223,.24,materials.steel,.017);ring(nozzle,.174,.955,materials.copper,.012);
 parts.push({node:holder,amount:.55,id:'mig-diffuser'},{node:tip,amount:1.3,id:'mig-tip'},{node:nozzle,amount:2.3,id:'mig-nozzle'});
 }else{
 tube(body,[[0,.12,0],[0,.6,0],[.1,.87,0],[.35,1.02,0]],.105,materials.rubber);
 const head=new THREE.Group();head.position.set(.36,1.04,0);head.rotation.z=-1.05;body.add(head);
 cylinder(head,.145,.16,.35,materials.rubber,0);
 const back=new THREE.Group();head.add(back);cylinder(back,.085,.13,.7,materials.rubber,-.5);ring(back,.12,-.19,materials.darkSteel,.017);
 const collet=new THREE.Group();head.add(collet);cylinder(collet,.05,.05,.32,materials.copper,.08);
 const insulator=new THREE.Group();head.add(insulator);lathe(insulator,[[.09,.15],[.16,.15],[.17,.22],[.16,.26],[.09,.26],[.09,.15]],new THREE.MeshStandardMaterial({color:0xe3ded0,roughness:.65}));
 const holder=new THREE.Group();head.add(holder);cylinder(holder,.095,.105,.32,materials.copper,.34);for(let i=0;i<7;i++)ring(holder,.104,.23+i*.028,materials.brass,.009);
 const nozzle=new THREE.Group();head.add(nozzle);lathe(nozzle,[[.14,.23],[.16,.28],[.17,.45],[.205,.87],[.20,.92],[.155,.92],[.15,.85],[.115,.42],[.10,.28],[.14,.23]],materials.ceramic);
 const electrode=new THREE.Group();head.add(electrode);cylinder(electrode,.015,.015,.9,materials.steel,.62);cylinder(electrode,0,.015,.09,materials.steel,1.115);
 parts.push({node:back,amount:-1.25,id:'tig-backcap'},{node:collet,amount:-.6,id:'tig-collet'},{node:insulator,amount:.4,id:'tig-insulator'},{node:holder,amount:.95,id:'tig-body'},{node:nozzle,amount:1.65,id:'tig-cup'},{node:electrode,amount:2.0,id:'electrode'});
 }
 return {group,parts};
}
function studio(renderer){
 const env=new THREE.Scene();env.background=new THREE.Color(0x60675b);
 const lights=[{p:[-4,4,3],s:[3,7],c:0xffffff},{p:[4,2,-1],s:[2,6],c:0xb8c3ae},{p:[1,-3,4],s:[3,2],c:0x9c6341}];
 for(const l of lights){const m=mesh(new THREE.PlaneGeometry(...l.s),new THREE.MeshBasicMaterial({color:l.c}),env,...l.p);m.lookAt(0,0,0);}
 const pmrem=new THREE.PMREMGenerator(renderer);const target=pmrem.fromScene(env,.04);pmrem.dispose();env.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});return target;
}

export function createAssembly(el,{onSelect,onProgress,onPlayChange}){
 let renderer;
 try{renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});}catch{return null;}
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.setClearColor(0,0);renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.45;
 el.appendChild(renderer.domElement);renderer.domElement.setAttribute('aria-hidden','true');
 const scene=new THREE.Scene(),env=studio(renderer);scene.environment=env.texture;
 scene.add(new THREE.HemisphereLight(0xdfead4,0x252c20,2));
 const key=new THREE.DirectionalLight(0xffffff,4);key.position.set(-3,5,5);scene.add(key);
 const edge=new THREE.DirectionalLight(0xffb87d,2);edge.position.set(4,0,-3);scene.add(edge);
 const camera=new THREE.PerspectiveCamera(32,1,.1,60);camera.position.set(0,0,11);camera.lookAt(0,0,0);
 const models={mig:makeTorch('mig',false),tig:makeTorch('tig',false)};
 for(const model of Object.values(models)){scene.add(model.group);for(const p of model.parts){p.node.userData.partId=p.id;p.node.traverse(o=>{if(o.material){o.material=o.material.clone();o.userData.partId=p.id;}});}}
 let family='mig',progress=0,target=0,visible=false,dirty=true,started=false,playing=false,start=0,yaw=-.4,tilt=0,down=null,activeId='';
 models.tig.group.visible=false;
 const resize=()=>{const {width,height}=el.getBoundingClientRect();if(!width||!height)return;renderer.setSize(width,height,false);camera.aspect=width/height;camera.position.z=camera.aspect<1?14:camera.aspect<1.7?12.5:10.5;camera.updateProjectionMatrix();dirty=true;};
 new ResizeObserver(resize).observe(el);resize();
 function setPlaying(value){playing=value;start=performance.now();onPlayChange?.(value);dirty=true;}
 new IntersectionObserver(([e])=>{visible=e.isIntersecting;dirty=true;if(visible&&!started){started=true;if(!reduced.matches)setPlaying(true);else{target=.6;onProgress?.(60);}}},{threshold:.15}).observe(el);
 const raycaster=new THREE.Raycaster();
 el.addEventListener('pointerdown',e=>{down={x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY};});
 el.addEventListener('pointermove',e=>{if(!down)return;const dx=e.clientX-down.lastX; yaw+=dx*.009;tilt=THREE.MathUtils.clamp(tilt+(e.clientY-down.lastY)*.002,-.35,.35);down.lastX=e.clientX;down.lastY=e.clientY;dirty=true;});
 el.addEventListener('pointerup',e=>{if(!down)return;const click=Math.hypot(e.clientX-down.x,e.clientY-down.y)<5;down=null;if(!click)return;const r=el.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const hit=raycaster.intersectObjects(models[family].group.children,true).find(x=>x.object.userData.partId&&x.object.userData.partId!=='electrode');if(hit)onSelect(hit.object.userData.partId);});
 el.addEventListener('pointercancel',()=>down=null);el.addEventListener('pointerleave',()=>down=null);
 renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();visible=false;el.classList.add('unavailable');});
 reduced.addEventListener('change',()=>{if(reduced.matches)setPlaying(false);dirty=true;});
 function render(now){requestAnimationFrame(render);if(!visible||document.hidden)return;
  if(playing){const t=(now-start)/5000;if(t>=1){target=0;setPlaying(false);}else target=.5-.5*Math.cos(t*Math.PI*2);onProgress?.(Math.round(target*100));}
  const moving=Math.abs(target-progress)>.0004;if(!dirty&&!moving&&!playing)return;progress=reduced.matches?target:THREE.MathUtils.lerp(progress,target,.12);
  const model=models[family];model.group.position.set((camera.aspect<1?.35:.9)+progress*.5,-.5-progress*.7,0);model.group.rotation.set(.16+tilt,yaw,1.12);model.group.scale.setScalar(.94);
  for(const p of model.parts){p.node.position.y=progress*p.amount;p.node.traverse(o=>{if(o.material?.emissive){o.material.emissive.setHex(p.id===activeId?0x59301c:0x000000);o.material.emissiveIntensity=.45;}});}
  renderer.render(scene,camera);el.classList.add('ready');dirty=false;
 }
 requestAnimationFrame(render);
 return {
  setFamily(value){if(value===family)return;family=value;for(const [key,m] of Object.entries(models))m.group.visible=key===family;dirty=true;},
  setProgress(value){setPlaying(false);target=THREE.MathUtils.clamp(Number(value)/100,0,1);dirty=true;},
  toggle(){if(reduced.matches){target=target>.5?0:1;onProgress?.(target*100);dirty=true;}else setPlaying(!playing);},
  highlight(id){activeId=id;dirty=true;}
 };
}
