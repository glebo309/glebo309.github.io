import {THREE,materials as m,mesh,cylinder,ring,lathe,makeTorch} from './models.mjs';
import {createPart} from './part-models.mjs';

export function setExplosion(model,progress){for(const p of model.parts)p.node.position.copy(p.rest).addScaledVector(p.offset,progress);}
export function makeInspectionTorch(family){
 if(family==='tig'){
  const model=makeTorch('tig',false);
  for(const p of model.parts){p.rest=p.node.position.clone();p.offset=new THREE.Vector3(0,p.amount,0);p.node.traverse(o=>{if(o.isMesh){o.userData.partId=p.id;o.material=o.material.clone();}});}
  return model;
 }
 const group=new THREE.Group(),parts=[];
 // The handle is context. The seven service components are independent meshes.
 const grip=lathe(group,[[.14,-1.9],[.23,-1.85],[.31,-1.65],[.33,-1.3],[.31,-.65],[.27,-.18],[.2,.09],[.15,.11]],m.rubber);grip.scale.z=.78;
 for(let i=0;i<11;i++){const rib=ring(group,.29,-1.55+i*.1,m.grip,.014);rib.scale.z=.8;}
 cylinder(group,.19,.22,.14,m.grip,-.1);
 for(const y of [-1.62,-.25]){const screw=mesh(new THREE.CylinderGeometry(.026,.026,.015,16),m.steel,group,0,y,.25);screw.rotation.x=Math.PI/2;}
 for(let i=0;i<6;i++)cylinder(group,.14-i*.007,.15-i*.007,.09,m.rubber,-1.94-i*.09);
 function add(id,parent,scale,position,offset,rotation=0){const node=createPart(id,{inspection:false});node.scale.setScalar(scale);node.position.set(...position);node.rotation.z=rotation;parent.add(node);parts.push({id,node,rest:node.position.clone(),offset:new THREE.Vector3(...offset)});return node;}
 add('mig-neck',group,.75,[0,.85,0],[.1,.5,0]);
 const head=new THREE.Group();head.position.set(.6,1.525,0);head.rotation.z=-Math.PI/4;group.add(head);
 add('mig-diffuser',head,.60,[0,.36,0],[0,.65,0]);
 add('mig-tip',head,.45,[0,1.12,0],[0,1.25,0]);
 add('mig-nozzle',head,.78,[0,.74,0],[0,3.1,0]);
 add('mig-trigger',group,.52,[0,-.65,.28],[-.45,-.05,1.1]);
 add('mig-cable',group,.8,[0,-3.6,0],[.65,-.5,-.1]);
 add('mig-liner',group,.9,[0,-2.8,-.04],[-1.05,-.15,.5]);
 group.rotation.set(.22,-.3,1.75);
 return {group,parts};
}
