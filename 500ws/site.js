'use strict';
// A fixed outer space prevents content jumping when the visible header contracts.
const masthead = document.querySelector('.site-header');
function syncHeader(){masthead?.classList.toggle('is-compact',window.scrollY>48);}
syncHeader();
window.addEventListener('scroll',syncHeader,{passive:true});
window.addEventListener('pageshow',syncHeader);

const toggle = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#site-nav');
function closeMenu(){navigation?.classList.remove('open');toggle?.setAttribute('aria-expanded','false');if(toggle)toggle.textContent='Menu';document.body.classList.remove('menu-open');}
toggle?.addEventListener('click',()=>{const open=toggle.getAttribute('aria-expanded')!=='true';toggle.setAttribute('aria-expanded',String(open));toggle.textContent=open?'Close':'Menu';navigation.classList.toggle('open',open);document.body.classList.toggle('menu-open',open);});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&toggle?.getAttribute('aria-expanded')==='true'){closeMenu();toggle.focus();}});
navigation?.querySelectorAll('a').forEach(link=>link.addEventListener('click',closeMenu));
window.matchMedia('(min-width: 851px)').addEventListener('change',event=>{if(event.matches)closeMenu();});
for(const group of document.querySelectorAll('[data-filter-group]')){
 let selected='all';
 const target=document.getElementById(group.dataset.filterGroup);
 const items=[...target.querySelectorAll('[data-category]')];
 const input=document.querySelector(`[data-search="${target.id}"]`);
 const count=document.querySelector(`[data-count="${target.id}"]`);
 const empty=document.querySelector(`[data-empty="${target.id}"]`);
 function apply(){let visible=0;const query=(input?.value||'').trim().toLocaleLowerCase();for(const item of items){const match=(selected==='all'||item.dataset.category.split('|').includes(selected))&&item.textContent.toLocaleLowerCase().includes(query);item.hidden=!match;if(match)visible++;}if(count){const noun=target.dataset.noun||'results';count.textContent=`${visible} ${visible===1?(noun==='stories'?'story':noun.replace(/s$/,'')):noun}`;}if(empty)empty.hidden=visible!==0;}
 for(const button of group.querySelectorAll('button'))button.addEventListener('click',()=>{selected=button.dataset.filter;for(const sibling of group.querySelectorAll('button'))sibling.setAttribute('aria-pressed',String(sibling===button));apply();});
 input?.addEventListener('input',apply);apply();
}
// Calendar dates are evaluated in the chapter's local time, not the visitor's timezone.
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Zurich',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
for(const event of document.querySelectorAll('[data-event-date]')){
 const upcoming=event.dataset.eventDate>=today;
 event.dataset.category=upcoming?'upcoming':'past';
 const destination=document.querySelector(upcoming?'#upcoming-events':'#past-events');
 if(destination)destination.append(event);
}
const upcoming=document.querySelector('#upcoming-events');
const noEvents=document.querySelector('#no-upcoming');
if(upcoming&&noEvents)noEvents.hidden=upcoming.children.length>0;
