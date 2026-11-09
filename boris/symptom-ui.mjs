import {symptoms,symptomCopy,selectedSymptom,symptomEnquiryURL,symptomSelectionQuery} from './symptoms.mjs?v=guide-1';
import {parts} from './teile/data.mjs';
import {localPart} from './teile/i18n.mjs?v=guide-1';
export function initSymptoms({page,getLanguage,onSelect=()=>{}}){
 const root=document.querySelector('#symptom-guide');
 let selected=selectedSymptom(location.search,getLanguage()),family=selected?.family||'mig';
 root.innerHTML=`<div class="symptom-heading"><div><p class="eyebrow" data-symptom-copy="tag"></p><h2 data-symptom-copy="title"></h2></div><p data-symptom-copy="intro"></p></div><div class="symptom-top"><label><span data-symptom-copy="process"></span><select id="symptom-process"><option value="mig">MIG / MAG</option><option value="tig">WIG / TIG</option></select></label><button type="button" class="symptom-clear" data-symptom-copy="clear"></button></div><div class="symptom-options" role="group"></div><div class="symptom-result" aria-live="polite" hidden><p class="symptom-result-title" data-symptom-copy="possible"></p><div class="symptom-parts"></div><p class="symptom-note" data-symptom-copy="note"></p><a class="symptom-enquiry" data-symptom-copy="enquire"></a></div>`;
 function updateURL(){const u=new URL(location.href);u.search=symptomSelectionQuery(u.search,selected?.id).toString();history.replaceState(null,'',u);window.dispatchEvent(new Event('symptomchange'));}
 function render(){
  const lang=getLanguage(),t=symptomCopy[lang];root.setAttribute('aria-label',t.title);if(selected)selected=selectedSymptom('?symptom='+selected.id,lang);
  root.querySelectorAll('[data-symptom-copy]').forEach(e=>e.textContent=t[e.dataset.symptomCopy]);
  root.querySelector('#symptom-process').value=family;
  root.querySelector('.symptom-options').setAttribute('aria-label',t.title);
  root.querySelector('.symptom-options').innerHTML=symptoms.filter(s=>s.family===family).map((s,i)=>`<button type="button" data-symptom="${s.id}" aria-pressed="${s.id===selected?.id}"><span>${String(i+1).padStart(2,'0')}</span>${t[s.id]}<b aria-hidden="true">↗</b></button>`).join('');
  root.querySelector('.symptom-clear').hidden=!selected;
  root.querySelector('.symptom-result').hidden=!selected;
  if(selected){
   root.querySelector('.symptom-parts').innerHTML=selected.partIds.map(id=>{const name=localPart(parts.find(p=>p.id===id),lang).name;return `<a data-symptom-part="${id}" href="${page==='parts'?'': 'teile/'}?lang=${lang}&symptom=${selected.id}#${id}"><span>${name}</span><small>${t.view} ↗</small></a>`;}).join('');
   const href=symptomEnquiryURL(selected.id,lang);root.querySelector('.symptom-enquiry').href=page==='parts'?href:href.slice(3);
  }
 }
 root.addEventListener('click',e=>{
  const option=e.target.closest('[data-symptom]');
  if(option){selected=selectedSymptom('?symptom='+option.dataset.symptom,getLanguage());updateURL();render();onSelect(selected,selected.partIds[0]);root.querySelector(`[data-symptom="${selected.id}"]`).focus({preventScroll:true});}
  if(e.target.closest('.symptom-clear')){selected=null;updateURL();render();onSelect(null);root.querySelector('#symptom-process').focus({preventScroll:true});}
  const part=e.target.closest('[data-symptom-part]');if(part&&page==='parts'){e.preventDefault();onSelect(selected,part.dataset.symptomPart);document.querySelector('.assembly').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
  if(e.target.closest('.symptom-enquiry')&&page==='main'){e.preventDefault();document.querySelector('#contact').scrollIntoView({behavior:'smooth'});history.replaceState(null,'','#contact');}
 });
 root.querySelector('#symptom-process').addEventListener('change',e=>{family=e.target.value;selected=null;updateURL();render();onSelect(null,null,family);});
 window.addEventListener('symptomremoved',()=>{selected=null;render();onSelect(null);});
 render();return {translate:render,current:()=>selected,setFamily(value){if(value===family)return;family=value;selected=null;updateURL();render();}};
}
