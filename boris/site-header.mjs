import {copy} from './content.mjs?v=about-3';
export function initHeader({page,lang,onLanguage}){
 const root=document.querySelector('.site-header'),nav=root.querySelector('#navigation'),menu=root.querySelector('.menu');
 let language=lang;
 function close(){nav.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label',copy[language].menu);}
 function update(value){language=value;const t=copy[value],home=page==='main'?'':`../?lang=${value}`;
  root.querySelectorAll('[data-header-copy]').forEach(el=>el.textContent=t[el.dataset.headerCopy]);
  root.querySelector('.brand').href=page==='main'?'#top':home;
  root.querySelector('#language').value=value;root.querySelector('#language').setAttribute('aria-label',t.languageLabel);
  for(const [key,section] of [['nav1','services'],['nav2','torches'],['nav3','about'],['nav4','contact']])root.querySelector(`[data-header-copy="${key}"]`).href=`${home}#${section}`;
  root.querySelector('[data-header-copy="navParts"]').href=page==='main'?`teile/?lang=${value}`:`?lang=${value}`;
  root.querySelector('.header-cta').href=`${home}#contact`;
  menu.setAttribute('aria-label',t[nav.classList.contains('open')?'close':'menu']);
 }
 menu.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open));menu.setAttribute('aria-label',copy[language][open?'close':'menu']);});
 nav.querySelectorAll('a').forEach(a=>a.addEventListener('click',close));
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&nav.classList.contains('open')){close();menu.focus();}});
 matchMedia('(min-width:1101px)').addEventListener('change',e=>{if(e.matches)close();});
 root.querySelector('#language').addEventListener('change',e=>onLanguage(e.target.value));
 update(lang);return{update};
}
