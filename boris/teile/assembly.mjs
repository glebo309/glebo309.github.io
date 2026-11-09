import {THREE,makeTorch} from './models.mjs';
import {createReveal} from './reveal.mjs';
import {createViewer} from './viewer.mjs';
import {createPart} from './part-models.mjs';
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
export function createAssembly(el,{onSelect}){
 const models={mig:makeTorch('mig',false),tig:makeTorch('tig',false)},reveals={mig:createReveal(),tig:createReveal()};
 let family='mig',progress=-1;
 for(const model of Object.values(models)){
  model.group.rotation.set(.3,-.45,1.12);
  for(const p of model.parts){p.node.position.y=p.amount;p.node.traverse(o=>{if(o.material){o.material=o.material.clone();o.userData.partId=p.id;}});}
  model.group.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(model.group);model.group.position.sub(box.getCenter(new THREE.Vector3()));model.radius=box.getBoundingSphere(new THREE.Sphere()).radius;
  for(const p of model.parts)p.node.position.y=0;
 }
 const viewer=createViewer(el,{onPick:onSelect,tick(now,visible){const p=reveals[family].update(now,visible,reduced.matches);if(p===progress)return false;progress=p;for(const part of models[family].parts)part.node.position.y=p*part.amount;return true;}});
 function mount(){viewer.setObject(models[family].group);viewer.setRadius(models[family].radius);progress=-1;}
 mount();
 return {...viewer,setFamily(value){if(value===family)return;family=value;mount();},highlight(id){for(const part of models[family].parts)part.node.traverse(o=>{if(o.material?.emissive){o.material.emissive.setHex(part.id===id?0x9b431b:0);o.material.emissiveIntensity=.6;}});viewer.refresh();}};
}
export function createPartViewer(el){const viewer=createViewer(el);const cache=new Map();let selected='';return {...viewer,show(id){if(id===selected)return;selected=id;if(!cache.has(id))cache.set(id,createPart(id));viewer.setObject(cache.get(id));}};}
