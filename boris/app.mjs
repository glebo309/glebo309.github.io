import {copy, resolveLanguage, requestText} from './content.mjs';
let lang=resolveLanguage(new URL(location.href).searchParams.get('lang'));
let product='mig';
const menu=document.querySelector('.menu');
const navigation=document.querySelector('#navigation');
function updateProduct(){
 const t=copy[lang];
 document.querySelector('#product-title').textContent=t[product+'Title'];
 document.querySelector('#product-text').textContent=t[product+'Text'];
 document.querySelector('.product-watermark').textContent=product==='mig'?'MIG':'TIG';
 document.querySelector('#product-panel').setAttribute('aria-labelledby',product+'-tab');
 document.querySelectorAll('[data-product]').forEach(b=>{const active=b.dataset.product===product;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;});
}
function translate(){
 const t=copy[lang];
 document.documentElement.lang=lang==='zh'?'zh-Hans':lang;
 document.title=t.title;
 document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=t[e.dataset.i18n]);
 document.querySelectorAll('[data-list]').forEach(e=>{e.replaceChildren(...t[e.dataset.list].split('|').map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));});
 document.querySelectorAll('[data-placeholder]').forEach(e=>e.placeholder=t[e.dataset.placeholder]);
 document.querySelectorAll('[data-alt]').forEach(e=>e.alt=t[e.dataset.alt]);
 document.querySelectorAll('[data-lang]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.lang===lang)));
 menu.setAttribute('aria-label',navigation.classList.contains('open')?t.close:t.menu);
 if(!document.querySelector('#form-status').hidden) document.querySelector('#form-status').textContent=t.success;
 updateProduct();
}
document.querySelectorAll('[data-lang]').forEach(b=>b.addEventListener('click',()=>{lang=resolveLanguage(b.dataset.lang);const url=new URL(location.href);url.searchParams.set('lang',lang);history.replaceState(null,'',url);translate();}));
menu.addEventListener('click',()=>{const open=navigation.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',copy[lang][open?'close':'menu']);});
navigation.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{navigation.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label',copy[lang].menu);}));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&navigation.classList.contains('open')){navigation.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label',copy[lang].menu);menu.focus();}});
function selectProduct(value){product=value;updateProduct();window.dispatchEvent(new CustomEvent('productchange',{detail:product}));}
document.querySelectorAll('[data-product]').forEach(b=>{b.addEventListener('click',()=>selectProduct(b.dataset.product));b.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();selectProduct(e.key==='Home'?'mig':e.key==='End'?'tig':product==='mig'?'tig':'mig');document.querySelector('#'+product+'-tab').focus();}});});
document.querySelectorAll('[data-service]').forEach(a=>a.addEventListener('click',()=>{document.querySelector('[name=service]').value=a.dataset.service;if(a.id==='product-enquiry') document.querySelector('[name=process]').value=product==='mig'?'MIG/MAG':'WIG/TIG';}));
document.querySelector('#enquiry').addEventListener('submit',e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));if(data.process==='?')data.process=copy[lang].other;const blob=new Blob(['\uFEFF'+requestText(lang,data)],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='BORIS-'+lang+'-Anfrage.txt';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);const status=document.querySelector('#form-status');status.hidden=false;status.textContent=copy[lang].success;});
document.querySelector('#year').textContent=new Date().getFullYear();
translate();
