import {initHeader} from './site-header.mjs?v=enquiry-2';
import {initEnquiry} from './enquiry-ui.mjs?v=enquiry-2';
import {initialLanguage,rememberLanguage} from './language.mjs';
import {copy, resolveLanguage, requestText} from './content.mjs?v=enquiry-2';
let lang=initialLanguage(copy);
let product='mig';
const header=initHeader({page:'main',lang,onLanguage:value=>{lang=resolveLanguage(value);rememberLanguage(lang);translate();}});
const enquiry=initEnquiry(()=>lang);
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
 header.update(lang);
 document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=t[e.dataset.i18n]);
 document.querySelectorAll('[data-list]').forEach(e=>{e.replaceChildren(...t[e.dataset.list].split('|').map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));});
 document.querySelectorAll('[data-placeholder]').forEach(e=>e.placeholder=t[e.dataset.placeholder]);
 document.querySelectorAll('[data-alt]').forEach(e=>e.alt=t[e.dataset.alt]);
 enquiry.translate();
 updateProduct();
}
function selectProduct(value){product=value;updateProduct();window.dispatchEvent(new CustomEvent('productchange',{detail:product}));}
document.querySelectorAll('[data-product]').forEach(b=>{b.addEventListener('click',()=>selectProduct(b.dataset.product));b.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();selectProduct(e.key==='Home'?'mig':e.key==='End'?'tig':product==='mig'?'tig':'mig');document.querySelector('#'+product+'-tab').focus();}});});
document.querySelectorAll('[data-service]').forEach(a=>a.addEventListener('click',()=>{document.querySelector('[name=service]').value=a.dataset.service;if(a.id==='product-enquiry') document.querySelector('[name=process]').value=product==='mig'?'MIG/MAG':'WIG/TIG';}));
document.querySelector('#year').textContent=new Date().getFullYear();
translate();
