import {updateMetadata} from '../metadata.mjs?v=about-3';
import {initSymptoms} from '../symptom-ui.mjs?v=about-3';
import {selectedSymptom,symptomEnquiryURL} from '../symptoms.mjs?v=about-3';
import {initHeader} from '../site-header.mjs?v=about-3';
import {partEnquiryURL} from '../enquiry.mjs?v=about-3';
import {enquiryCopy} from '../enquiry-copy.mjs?v=about-3';
import {initialLanguage,rememberLanguage} from '../language.mjs';
import {parts,selectPart,catalogueLink} from './data.mjs';
import {ui,localPart} from './i18n.mjs?v=about-3';
import {createAssembly,createPartViewer} from './assembly.mjs?v=about-3';
const $=s=>document.querySelector(s);
let lang=initialLanguage(ui);
const header=initHeader({page:'parts',lang,onLanguage:value=>{lang=value;rememberLanguage(lang);translate();show(selected);}});
let family='mig',selected=parts[0],assembly=null,partViewer=null;
let activeSymptom=selectedSymptom(location.search,lang);
const symptomGuide=initSymptoms({page:'parts',getLanguage:()=>lang,onSelect:(symptom,id,newFamily)=>{activeSymptom=symptom;if(id)choose(parts.find(p=>p.id===id));else if(newFamily)choose(selectPart(newFamily,''));else show(selected);}});
const families={mig:parts.filter(p=>p.family==='mig').map(p=>p.id),tig:['tig-cup','tig-body','tig-insulator','tig-collet','tig-backcap']};
function renderAtlas(){const t=ui[lang];$('#atlas').innerHTML=parts.map(p=>`<tr><td><a href="#${p.id}">${p.family==='mig'?'MIG':'TIG'} / ${localPart(p,lang).name}</a></td><td><a href="${catalogueLink(p)}" target="_blank" rel="noopener">${p.reference.title} ↗</a></td><td>${p.reference.page} / ${p.reference.key==='b40'?t.none:p.reference.printed}</td><td>${p.reference.position}</td></tr>`).join('');}
function translate(){const t=ui[lang];document.documentElement.lang=lang==='zh'?'zh-Hans':lang;updateMetadata('parts',lang,t.title);document.querySelectorAll('[data-copy]').forEach(e=>e.textContent=t[e.dataset.copy]);document.querySelectorAll('[data-copy-html]').forEach(e=>e.innerHTML=t[e.dataset.copyHtml]);document.querySelectorAll('[data-zoom]').forEach(b=>b.setAttribute('aria-label',t[b.dataset.zoom==='in'?'zoomIn':'zoomOut']));header.update(lang);symptomGuide.translate();activeSymptom=selectedSymptom(location.search,lang);document.querySelectorAll('[data-enquiry-copy]').forEach(e=>e.textContent=enquiryCopy[lang][e.dataset.enquiryCopy]);$('#previous').setAttribute('aria-label',t.previous);$('#next').setAttribute('aria-label',t.next);$('footer a').href=`../?lang=${lang}#contact`;renderAtlas();}
function show(part){
 symptomGuide.setFamily(part.family);activeSymptom=selectedSymptom(location.search,lang);selected=part;family=part.family;$('#part-enquiry').href=partEnquiryURL(part.id,lang);if(activeSymptom?.family===family){const u=new URL($('#part-enquiry').href);u.searchParams.set('symptom',activeSymptom.id);$('#part-enquiry').href=u;}const t=ui[lang],local=localPart(part,lang);
 const list=parts.filter(p=>p.family===family),index=list.indexOf(part);
 document.querySelectorAll('[data-family]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.family===family)));
 $('#part-list').innerHTML=list.map((p,i)=>`<button data-part="${p.id}" aria-pressed="${p.id===part.id}"><span>${String(i+1).padStart(2,'0')}</span>${localPart(p,lang).name}</button>`).join('');
 $('#part-number').textContent=`${family==='mig'?'MIG / MAG':'WIG / TIG'} · ${String(index+1).padStart(2,'0')} / ${String(list.length).padStart(2,'0')}`;
 $('#kind').textContent=local.kind;partViewer?.show(part.id);$('#illustration').setAttribute('aria-label',local.name);
 $('#english').textContent=part.english.toUpperCase();$('#name').textContent=local.name;$('#issue').textContent=local.issue;
 $('#reference-title').textContent=part.reference.title;$('#pdf-page').textContent=part.reference.page;$('#position').textContent=part.reference.position;
 $('#printed').textContent=part.reference.key==='b40'?t.old:`${t.printed}: ${part.reference.printed}`;$('#where').textContent=local.where;
 $('#catalogue').href=catalogueLink(part);$('#failure-source').href=part.evidence;
 $('#assembly-parts').innerHTML=families[family].map(id=>{const p=parts.find(p=>p.id===id);return `<button data-assembly-part="${id}" aria-pressed="${id===part.id}">${localPart(p,lang).name}</button>`;}).join('');
 assembly?.setFamily(family);assembly?.highlight(part.id,activeSymptom?.partIds||[]);
 document.querySelectorAll("[data-part],[data-assembly-part]").forEach(b=>b.classList.toggle("symptom-match",!!activeSymptom?.partIds.includes(b.dataset.part||b.dataset.assemblyPart)));assembly?.setLabels(list.map(p=>({id:p.id,name:localPart(p,lang).name})));
}
function choose(part){show(part);history.replaceState(null,'',`#${part.id}`);}
$('.families').addEventListener('click',e=>{const b=e.target.closest('[data-family]');if(b)choose(selectPart(b.dataset.family,selected.id));});
$('#part-list').addEventListener('click',e=>{const b=e.target.closest('[data-part]');if(b){choose(selectPart(family,b.dataset.part));document.querySelector(`[data-part="${b.dataset.part}"]`).focus({preventScroll:true});}});
$('#assembly-parts').addEventListener('click',e=>{const b=e.target.closest('[data-assembly-part]');if(b)choose(selectPart(family,b.dataset.assemblyPart));});
function step(delta){const list=parts.filter(p=>p.family===family);choose(list[(list.indexOf(selected)+delta+list.length)%list.length]);}
$('#previous').addEventListener('click',()=>step(-1));$('#next').addEventListener('click',()=>step(1));
function fromHash(){const target=parts.find(p=>p.id===location.hash.slice(1));show(target||parts.find(p=>p.id===activeSymptom?.partIds[0])||parts[0]);if(target)document.querySelector(families[target.family].includes(target.id)?'.assembly':'.explorer').scrollIntoView({behavior:'instant',block:'start'});}
window.addEventListener('hashchange',fromHash);window.addEventListener('pageshow',()=>requestAnimationFrame(fromHash));translate();fromHash();
try{assembly=createAssembly($('#assembly-stage'),{onSelect:id=>choose(selectPart(family,id))});assembly.setFamily(family);assembly.highlight(selected.id,activeSymptom?.partIds||[]);assembly.setLabels(parts.filter(p=>p.family===family).map(p=>({id:p.id,name:localPart(p,lang).name})));}catch(error){console.warn('Assembly view unavailable',error);}
try{partViewer=createPartViewer($('#illustration'));partViewer.show(selected.id);}catch(error){console.warn('Part view unavailable',error);}
document.querySelectorAll('[data-view]').forEach(bar=>bar.addEventListener('click',e=>{const viewer=bar.dataset.view==='assembly'?assembly:partViewer;if(e.target.closest('[data-reset]'))viewer?.reset();const button=e.target.closest('[data-zoom]');if(button)viewer?.zoom(button.dataset.zoom==='in'?.8:1.25);}));
