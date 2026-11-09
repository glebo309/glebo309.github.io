import {copy,requestText} from './content.mjs';
import {recipient,selectedPart,validatePhotos,sendEnquiry} from './enquiry.mjs';
export function initEnquiry(getLanguage){
 const form=document.querySelector('#enquiry'),status=document.querySelector('#form-status'),send=form.querySelector('#send-enquiry');
 const photoInputs=[...form.querySelectorAll('input[type=file]')],urls=new Map();
 let state='',photoError='',busy=false,accepted=false;
 const initial=selectedPart(location.search,getLanguage());
 if(initial){form.elements.service.value='repair';form.elements.process.value=initial.process;}
 function data(){const result=Object.fromEntries(new FormData(form)),part=selectedPart(location.search,getLanguage());result.partName=part?.name||'';if(result.process==='?')result.process=copy[getLanguage()].other;return result;}
 function photos(){return photoInputs.flatMap(input=>[...input.files]);}
 function translate(){
  const t=copy[getLanguage()],part=selectedPart(location.search,getLanguage());
  form.querySelector('#selected-part').hidden=!part;
  form.querySelector('#part-id').value=part?.id||'';
  form.querySelector('#selected-part-name').textContent=part?`${part.process} · ${part.name}`:'';
  photoInputs.forEach((input,i)=>input.setAttribute('aria-label',`${t.photoLabel} ${i+1}`));
  const error=form.querySelector('#photo-error');error.hidden=!photoError;error.textContent=photoError?t[photoError]:'';
  status.hidden=!state;status.textContent=state?t[state==='accepted'?'success':state==='error'?'sendError':state]:'';
  status.classList.toggle('enquiry-status-error',['error','activation'].includes(state));
  send.querySelector('[data-i18n=submit]').textContent=busy?t.sending:t.submit;
  send.disabled=busy||accepted;
 }
 function preview(input){
  const slot=input.closest('.photo-slot'),img=slot.querySelector('img'),file=input.files[0];
  if(urls.has(input)){URL.revokeObjectURL(urls.get(input));urls.delete(input);}
  img.hidden=!file;slot.querySelector('.remove-photo').hidden=!file;
  slot.querySelector('.photo-filename').textContent=file?file.name:'';
  if(file){const url=URL.createObjectURL(file);urls.set(input,url);img.src=url;}else img.removeAttribute('src');
 }
 for(const input of photoInputs){
  input.addEventListener('change',()=>{photoError=validatePhotos(photos())||'';if(photoError)input.value='';preview(input);accepted=false;state='';translate();});
  input.closest('.photo-slot').querySelector('.remove-photo').addEventListener('click',()=>{input.value='';preview(input);photoError='';accepted=false;state='';translate();input.focus();});
 }
 form.querySelector('#remove-part').addEventListener('click',()=>{const url=new URL(location.href);url.searchParams.delete('part');history.replaceState(null,'',url);accepted=false;state='';translate();});
 form.addEventListener('input',()=>{if(!busy){accepted=false;state='';translate();}});
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||accepted)return;
  if(form.elements._honey.value)return;
  photoError=validatePhotos(photos())||'';if(photoError){translate();form.querySelector('#photo-error').scrollIntoView({block:'center'});return;}
  const fields=data(),payload=new FormData(form);
  for(const input of photoInputs)if(!input.files.length)payload.delete(input.name);
  payload.set('message',requestText(getLanguage(),fields));
  payload.set('_subject',`BORIS: ${copy[getLanguage()][fields.service]||copy[getLanguage()].question} / ${fields.process}${fields.partName?' / '+fields.partName:''}`);
  payload.set('_template','table');payload.set('language',getLanguage());
  busy=true;state='sending';translate();form.setAttribute('aria-busy','true');
  const controls=[...form.querySelectorAll('input,select,textarea,button')];controls.forEach(el=>el.disabled=true);
  state=await sendEnquiry(payload);busy=false;accepted=state==='accepted';
  controls.forEach(el=>el.disabled=false);form.removeAttribute('aria-busy');translate();
  status.tabIndex=-1;status.focus({preventScroll:true});
 });
 form.querySelector('#download-enquiry').addEventListener('click',()=>{
  if(!form.reportValidity())return;
  const blob=new Blob(['\uFEFF'+requestText(getLanguage(),data())],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=`BORIS-${getLanguage()}-Anfrage.txt`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);state='downloaded';translate();
 });
 window.addEventListener('pagehide',()=>{for(const url of urls.values())URL.revokeObjectURL(url);});
 translate();return{translate};
}
