import {THREE} from './models.mjs';
import {makeInspectionTorch,setExplosion} from './inspection-models.mjs';
import {createReveal} from './reveal.mjs';
import {createViewer} from './viewer.mjs?v=guide-1';
import {createPart} from './part-models.mjs';
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
export function createAssembly(el,{onSelect}){
 const models={mig:makeInspectionTorch('mig'),tig:makeInspectionTorch('tig')},reveals={mig:createReveal(),tig:createReveal()};
 let family='mig',progress=-1;
 for(const [key,model] of Object.entries(models)){
  if(key==='tig')model.group.rotation.set(.3,-.45,1.12);
  setExplosion(model,1);model.group.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(model.group);
  setExplosion(model,0);model.group.updateMatrixWorld(true);box.union(new THREE.Box3().setFromObject(model.group));
  const center=box.getCenter(new THREE.Vector3());model.group.position.sub(center);box.translate(center.negate());model.bounds=box;
 }
 const markers=new Map();
 for(const id of models.mig.parts.map(p=>p.id)){const button=document.createElement('button');button.className='part-marker';button.type='button';button.dataset.marker=id;button.addEventListener('click',()=>onSelect(id));el.append(button);markers.set(id,button);}
 const projected=new THREE.Vector3(),center=new THREE.Vector3();
 const viewer=createViewer(el,{onPick:onSelect,tick(now,visible){const p=reveals[family].update(now,visible,reduced.matches);if(p===progress)return false;progress=p;setExplosion(models[family],p);return true;},onRender(camera){
  for(const [id,button] of markers){button.hidden=family!=='mig';if(button.hidden)continue;const part=models.mig.parts.find(p=>p.id===id);new THREE.Box3().setFromObject(part.node).getCenter(center);projected.copy(center).project(camera);button.hidden=projected.z>1||Math.abs(projected.x)>.94||Math.abs(projected.y)>.92;if(!button.hidden){button.style.left=`${(projected.x+1)*50}%`;button.style.top=`calc(${(1-projected.y)*50}% - 25px)`;}}
 }});
 function mount(){viewer.setObject(models[family].group);viewer.setBounds(models[family].bounds);progress=-1;}
 mount();
 return {...viewer,setFamily(value){if(value===family)return;family=value;mount();},setLabels(items){for(const [i,item] of items.entries()){const b=markers.get(item.id);if(b){b.textContent=String(i+1).padStart(2,'0');b.setAttribute('aria-label',item.name);b.title=item.name;}}},highlight(id,related=[]){models[family].group.traverse(o=>{if(o.material?.emissive){o.material.emissive.setHex(o.userData.partId===id?0x9b431b:related.includes(o.userData.partId)?0x663015:0);o.material.emissiveIntensity=.6;}});for(const [key,b] of markers){b.setAttribute('aria-pressed',String(key===id));b.classList.toggle('symptom-match',related.includes(key));}viewer.refresh();}};
}
export function createPartViewer(el){const viewer=createViewer(el);const cache=new Map();let selected='';return {...viewer,show(id){if(id===selected)return;selected=id;if(!cache.has(id))cache.set(id,createPart(id));viewer.setObject(cache.get(id));}};}
