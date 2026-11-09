import {THREE,studio} from './models.mjs';
import {TrackballControls} from '../assets/TrackballControls.js';
export function createViewer(el,{tick=()=>false,onPick}={}){
 const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});
 renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;
 const canvas=renderer.domElement;canvas.setAttribute('aria-hidden','true');el.append(canvas);
 const scene=new THREE.Scene(),environment=studio(renderer);scene.environment=environment.texture;
 scene.add(new THREE.HemisphereLight(0xe8eee0,0x20251d,2));
 for(const [color,power,x,y,z] of [[0xffffff,4,-3,5,5],[0xffc9a1,2,4,0,-3]]){const light=new THREE.DirectionalLight(color,power);light.position.set(x,y,z);scene.add(light);}
 const camera=new THREE.PerspectiveCamera(35,1,.01,200);camera.position.z=8;
 const controls=new TrackballControls(camera,canvas);controls.rotateSpeed=3;controls.zoomSpeed=1.2;controls.panSpeed=.6;controls.staticMoving=true;controls.noPan=false;
 let dirty=true,visible=false,baseDistance=8,radius=1,object=null;
 controls.addEventListener('change',()=>dirty=true);
 function reset(){controls.target.set(0,0,0);camera.position.set(0,0,baseDistance);camera.up.set(0,1,0);camera.lookAt(controls.target);controls.update();dirty=true;}
 function fit(){const half=Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*Math.min(1,camera.aspect));baseDistance=radius/Math.sin(half);controls.minDistance=baseDistance*.18;controls.maxDistance=baseDistance*4;reset();}
 function resize(){const r=el.getBoundingClientRect();if(!r.width||!r.height)return;renderer.setSize(r.width,r.height,false);camera.aspect=r.width/r.height;camera.updateProjectionMatrix();controls.handleResize();fit();}
 new ResizeObserver(resize).observe(el);resize();
 new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;dirty=true;},{threshold:.25}).observe(el);
 let down=null;const pointers=new Set();const raycaster=new THREE.Raycaster();
 canvas.addEventListener('pointerdown',e=>{pointers.add(e.pointerId);if(pointers.size>1){if(down)down.moved=true;return;}down={x:e.clientX,y:e.clientY,moved:false};});
 canvas.addEventListener('pointermove',e=>{if(down&&Math.hypot(e.clientX-down.x,e.clientY-down.y)>5)down.moved=true;});
 canvas.addEventListener('pointerup',e=>{pointers.delete(e.pointerId);if(down&&!down.moved&&e.button===0&&onPick){const r=canvas.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);const hit=raycaster.intersectObjects(scene.children,true).find(h=>h.object.userData.partId&&h.object.userData.partId!=='electrode');if(hit)onPick(hit.object.userData.partId);}if(!pointers.size)down=null;});
 canvas.addEventListener('pointercancel',()=>{pointers.clear();down=null;});
 function zoom(factor){camera.position.sub(controls.target).multiplyScalar(factor).clampLength(controls.minDistance,controls.maxDistance).add(controls.target);controls.update();dirty=true;}
 function rotate(axis,angle){const q=new THREE.Quaternion().setFromAxisAngle(axis,angle);camera.position.sub(controls.target).applyQuaternion(q).add(controls.target);camera.up.applyQuaternion(q);controls.update();dirty=true;}
 el.addEventListener('keydown',e=>{const keys=['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','q','e','+','=','-','Home'];if(!keys.includes(e.key))return;e.preventDefault();if(e.key==='Home')reset();else if(['+','='].includes(e.key))zoom(.85);else if(e.key==='-')zoom(1.15);else{const axis=new THREE.Vector3();if(e.key==='q'||e.key==='e')axis.copy(camera.position).sub(controls.target).normalize();else if(e.key==='ArrowLeft'||e.key==='ArrowRight')axis.copy(camera.up).normalize();else axis.crossVectors(camera.up,camera.position.clone().sub(controls.target)).normalize();rotate(axis,['ArrowLeft','ArrowUp','q'].includes(e.key)?.15:-.15);}});
 canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();visible=false;el.classList.add('unavailable');el.classList.remove('ready');});
 function frame(now){requestAnimationFrame(frame);const active=visible&&!document.hidden;const changed=tick(now,active);if(!active)return;controls.update();if(!dirty&&!changed)return;renderer.render(scene,camera);dirty=false;el.classList.add('ready');}
 requestAnimationFrame(frame);
 return {scene,reset,zoom,refresh(){dirty=true;},setObject(next){if(object)scene.remove(object);object=next;scene.add(next);next.updateMatrixWorld(true);radius=new THREE.Box3().setFromObject(next).getBoundingSphere(new THREE.Sphere()).radius;fit();},setRadius(value){radius=value;fit();}};
}
