import {parts,selectPart,catalogueLink} from './data.mjs';
import {drawPart} from './drawings.mjs';
import {ui,localPart} from './i18n.mjs';
import {createAssembly} from './assembly.mjs';
const $=s=>document.querySelector(s);
let lang=new URL(location.href).searchParams.get('lang');if(!ui[lang])lang='de';
let family='mig',selected=parts[0],assembly=null,playing=false;
const families={mig:['mig-nozzle','mig-tip','mig-diffuser'],tig:['tig-cup','tig-body','tig-insulator','tig-collet','tig-backcap']};
function renderAtlas(){const t=ui[lang];$('#atlas').innerHTML=parts.map(p=>`<tr><td><a href="#${p.id}">${p.family==='mig'?'MIG':'TIG'} / ${localPart(p,lang).name}</a></td><td><a href="${catalogueLink(p)}" target="_blank" rel="noopener">${p.reference.title} ↗</a></td><td>${p.reference.page} / ${p.reference.key==='b40'?t.none:p.reference.printed}</td><td>${p.reference.position}</td></tr>`).join('');}
function translate(){const t=ui[lang];document.documentElement.lang=lang==='zh'?'zh-Hans':lang;document.title=t.title;document.querySelectorAll('[data-copy]').forEach(e=>e.textContent=t[e.dataset.copy]);document.querySelectorAll('[data-copy-html]').forEach(e=>e.innerHTML=t[e.dataset.copyHtml]);document.querySelectorAll('[data-lang]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lang===lang)));$('#previous').setAttribute('aria-label',t.previous);$('#next').setAttribute('aria-label',t.next);$('#explosion').setAttribute('aria-label',t.range);$('#animate').textContent=t[playing?'stop':'play'];$('.brand').href=`../?lang=${lang}`;$('header>a:last-child').href=`../?lang=${lang}`;$('footer a').href=`../?lang=${lang}#contact`;renderAtlas();}
function show(part){
 selected=part;family=part.family;const t=ui[lang],local=localPart(part,lang);
 const list=parts.filter(p=>p.family===family),index=list.indexOf(part);
 document.querySelectorAll('[data-family]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.family===family)));
 $('#part-list').innerHTML=list.map((p,i)=>`<button data-part="${p.id}" aria-pressed="${p.id===part.id}"><span>${String(i+1).padStart(2,'0')}</span>${localPart(p,lang).name}</button>`).join('');
 $('#part-number').textContent=`${family==='mig'?'MIG / MAG':'WIG / TIG'} · ${String(index+1).padStart(2,'0')} / ${String(list.length).padStart(2,'0')}`;
 $('#kind').textContent=local.kind;$('#illustration').innerHTML=drawPart(part.id);$('#illustration').setAttribute('aria-label',local.name);
 $('#english').textContent=part.english.toUpperCase();$('#name').textContent=local.name;$('#issue').textContent=local.issue;
 $('#reference-title').textContent=part.reference.title;$('#pdf-page').textContent=part.reference.page;$('#position').textContent=part.reference.position;
 $('#printed').textContent=part.reference.key==='b40'?t.old:`${t.printed}: ${part.reference.printed}`;$('#where').textContent=local.where;
 $('#catalogue').href=catalogueLink(part);$('#failure-source').href=part.evidence;
 $('#assembly-parts').innerHTML=families[family].map(id=>{const p=parts.find(p=>p.id===id);return `<button data-assembly-part="${id}" aria-pressed="${id===part.id}">${localPart(p,lang).name}</button>`;}).join('');
 assembly?.setFamily(family);assembly?.highlight(part.id);
}
function choose(part){show(part);history.replaceState(null,'',`#${part.id}`);}
$('.families').addEventListener('click',e=>{const b=e.target.closest('[data-family]');if(b)choose(selectPart(b.dataset.family,selected.id));});
$('#part-list').addEventListener('click',e=>{const b=e.target.closest('[data-part]');if(b){choose(selectPart(family,b.dataset.part));document.querySelector(`[data-part="${b.dataset.part}"]`).focus({preventScroll:true});}});
$('#assembly-parts').addEventListener('click',e=>{const b=e.target.closest('[data-assembly-part]');if(b)choose(selectPart(family,b.dataset.assemblyPart));});
function step(delta){const list=parts.filter(p=>p.family===family);choose(list[(list.indexOf(selected)+delta+list.length)%list.length]);}
$('#previous').addEventListener('click',()=>step(-1));$('#next').addEventListener('click',()=>step(1));
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>{lang=b.dataset.lang;const u=new URL(location.href);u.searchParams.set('lang',lang);history.replaceState(null,'',u);translate();show(selected);}));
function fromHash(){show(parts.find(p=>p.id===location.hash.slice(1))||parts[0]);}
window.addEventListener('hashchange',fromHash);translate();fromHash();
try{assembly=createAssembly($('#assembly-stage'),{onSelect:id=>choose(selectPart(family,id)),onProgress:value=>{$('#explosion').value=value;$('#explosion-value').textContent=`${value}%`;},onPlayChange:value=>{playing=value;$('#animate').textContent=ui[lang][value?'stop':'play'];$('#animate').setAttribute('aria-pressed',String(value));}});assembly?.setFamily(family);assembly?.highlight(selected.id);}catch(error){console.warn('Assembly view unavailable',error);}
if(!assembly){$('#animate').disabled=true;$('#explosion').disabled=true;}
$('#explosion').addEventListener('input',e=>{assembly?.setProgress(e.target.value);$('#explosion-value').textContent=`${e.target.value}%`;});
$('#animate').addEventListener('click',()=>assembly?.toggle());
