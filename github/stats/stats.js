'use strict';
const format = value => value == null ? 'Not collected' : Number(value).toLocaleString();
const dateText = value => value ? new Date(value).toLocaleString(undefined, {dateStyle:'medium',timeStyle:'short'}) : 'Not collected';
let rows = [];
function render() {
  const filter = document.getElementById('filter').value.toLowerCase();
  const target = document.getElementById('repositories');
  target.replaceChildren();
  for (const repo of rows.filter(r => r.name.toLowerCase().includes(filter))) {
    const tr = document.createElement('tr');
    const name = document.createElement('td');
    const link = document.createElement('a');
    link.href = 'https://github.com/' + repo.name.split('/').map(encodeURIComponent).join('/');
    link.textContent = repo.name.split('/').slice(1).join('/');
    name.append(link);
    const first = [repo.views_since, repo.clones_since].filter(Boolean).sort()[0];
    const note = document.createElement('small');
    note.textContent = first ? 'Recorded from ' + first : 'Awaiting daily records';
    name.append(note);
    if (repo.needs_retry) {const warning=document.createElement('small');warning.className='retry';warning.textContent='Some metrics awaiting retry';name.append(warning);}
    const details = document.createElement('details');
    const summary = document.createElement('summary');summary.textContent='Collection times';details.append(summary);
    for (const key of ['views','clones','downloads']) {const p=document.createElement('p');p.textContent=key+': '+dateText(repo[key+'_observed']);details.append(p);}
    name.append(details);tr.append(name);
    for (const key of ['views','clones','downloads','views_unique_window','clones_unique_window','stars']) {
      const td=document.createElement('td');td.textContent=format(repo[key]);tr.append(td);
    }
    target.append(tr);
  }
}
async function refresh() {
  try {
    const response = await fetch('./data.json', {cache:'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    if (data.schema !== 1 || !Array.isArray(data.repositories)) throw new Error('Unexpected data format');
    rows = data.repositories.sort((a,b) => (b.views || 0) - (a.views || 0));
    for (const key of ['views','clones','downloads']) {
      const values=rows.map(r=>r[key]).filter(v=>v!=null);
      document.getElementById(key).textContent=values.length?format(values.reduce((a,b)=>a+b,0)):'Not collected';
    }
    const updated=document.getElementById('updated');
    const stale=!data.last_collected_at || Date.now()-Date.parse(data.last_collected_at)>86400000;
    updated.textContent='Latest successful collection: '+dateText(data.last_collected_at)+(stale?' · Update overdue; showing saved figures.':' · Updated automatically.');
    updated.classList.toggle('warn',stale);
    document.getElementById('scope').textContent=rows.length+' public repositories · saved history';
    document.getElementById('load-error').hidden=true;
    render();
  } catch(error) {
    const message=document.getElementById('load-error');message.hidden=false;
    message.textContent='The latest snapshot could not be loaded. Please try again shortly.';
    document.getElementById('updated').textContent='Snapshot unavailable; any figures below are from the previous refresh.';
  }
}
document.getElementById('filter').addEventListener('input',render);
refresh();
setInterval(refresh,300000);
