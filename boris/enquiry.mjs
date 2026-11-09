import {parts} from './teile/data.mjs';
import {localPart} from './teile/i18n.mjs?v=guide-2';
export const recipient='glebo309@gmail.com';
export const endpoint=`https://formsubmit.co/ajax/${recipient}`;
const languages=['de','en','nl','zh','pl','bg'];
export function selectedPart(search,lang='de'){
 const part=parts.find(p=>p.id===new URLSearchParams(search).get('part'));
 if(!part)return null;
 const language=languages.includes(lang)?lang:'de';
 return {id:part.id,name:localPart(part,language).name,process:part.family==='mig'?'MIG/MAG':'WIG/TIG',catalogue:part.reference.title};
}
export function partEnquiryURL(id,lang='de'){
 const query=new URLSearchParams({lang:languages.includes(lang)?lang:'de'});
 if(parts.some(p=>p.id===id))query.set('part',id);
 return `../?${query}#contact`;
}
export function validatePhotos(files){
 if(files.length>3)return 'photoCount';
 if(files.some(f=>!['image/jpeg','image/png','image/webp'].includes(f.type)))return 'photoType';
 if(files.reduce((size,f)=>size+f.size,0)>9000000)return 'photoSize';
 return null;
}
export async function sendEnquiry(data,fetcher=fetch){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),30000);
 try{
  const response=await fetcher(endpoint,{method:'POST',headers:{Accept:'application/json'},body:data,signal:controller.signal});
  if(!response.ok)return 'error';
  const result=await response.json();
  if(result.success===true||result.success==='true')return 'accepted';
  return /activat/i.test(result.message||'')?'activation':'error';
 }catch{return 'error';}finally{clearTimeout(timeout);}
}
